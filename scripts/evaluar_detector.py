"""Evaluación cuantitativa del detector de toques con sesiones sintéticas etiquetadas.

Genera sesiones de un minuto en las que una mano simulada toca teclas y, a la
vez, hace todo lo que *no* debería sonar: arrastrar el dedo vecino, cambiar de
postura despacio, inclinar la mano, desplazarse entre teclas y alejarse o
acercarse a la cámara. A los 21 puntos se les suma ruido gaussiano, como el
temblor que tienen los puntos de MediaPipe. Como se sabe cuándo empezó cada
toque real (la "verdad"), se puede medir:

- **precisión**: de las notas que sonaron, cuántas eran toques reales;
- **sensibilidad** (*recall*): de los toques reales, cuántos sonaron;
- **F1**: media armónica de las dos;
- **latencia**: tiempo entre que el dedo empieza a bajar y suena la nota.

Produce ``docs/evaluacion.png`` y ``docs/RESULTADOS_EVALUACION.md``.

    python scripts/evaluar_detector.py            (≈1 minuto)
    python scripts/evaluar_detector.py --rapido   (menos sesiones, para probar)

Requiere matplotlib (``python -m pip install matplotlib``).
"""

from __future__ import annotations

import argparse
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Sequence, Tuple

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from piano_aereo import config  # noqa: E402
from piano_aereo.simulacion import mano_sintetica  # noqa: E402
from piano_aereo.toques import DetectorToques  # noqa: E402

FPS = 30
VENTANA = 0.35  # s tras el inicio del toque en que debe sonar para contar como acierto
RUIDO_BASE = 0.008  # desviación del ruido, en fracción del tamaño de la mano


# ------------------------------------------------------------------ sesiones
@dataclass
class Sesion:
    tiempos: np.ndarray  # (n,)
    puntos: np.ndarray  # (n, 21, 2) sin ruido
    tam: np.ndarray  # (n,) tamaño de la mano en píxeles
    toques: List[Tuple[float, int]]  # (instante en que empieza a bajar, dedo)


def _rampa(t: np.ndarray, inicio: float, subida: float, meseta: float, bajada: float) -> np.ndarray:
    """Curva 0 → 1 → 0 con tramos lineales."""
    y = np.clip((t - inicio) / subida, 0, 1)
    fin = inicio + subida + meseta
    return np.where(t > fin, np.clip(1 - (t - fin) / bajada, 0, 1), y)


def generar_sesion(azar: np.random.Generator, segundos: float = 60.0,
                   intensidad: Tuple[float, float] = (0.55, 1.0)) -> Sesion:
    """Una sesión etiquetada. ``intensidad``: rango de flexión de los toques (1 = dedo doblado del todo)."""
    t = np.arange(0, segundos, 1.0 / FPS)
    flexion = np.zeros((len(t), 5))
    cx = np.full(len(t), 640.0)
    inclinacion = np.zeros(len(t))
    toques: List[Tuple[float, int]] = []

    reloj = 1.0
    while reloj < segundos - 2.0:
        # A veces la mano viaja a otra tecla antes de tocar (nadie toca mientras se mueve).
        if azar.random() < 0.5:
            destino = float(np.clip(cx[t >= reloj][0] + azar.uniform(-260, 260), 300, 980))
            viaje = azar.uniform(0.25, 0.45)
            avance = np.clip((t - reloj) / viaje, 0, 1)
            cx = np.where(t >= reloj, cx[t >= reloj][0] + (destino - cx[t >= reloj][0]) * avance, cx)
            reloj += viaje + azar.uniform(0.08, 0.2)
        dedo = int(azar.choice(5, p=[0.12, 0.34, 0.26, 0.18, 0.10]))
        fuerza = azar.uniform(*intensidad)
        curva = _rampa(t, reloj, azar.uniform(0.07, 0.15), azar.uniform(0.05, 0.25), azar.uniform(0.08, 0.15))
        flexion[:, dedo] += fuerza * curva
        # El dedo vecino se arrastra un poco (dependencia mecánica de los tendones).
        for vecino in (dedo - 1, dedo + 1):
            if 1 <= vecino <= 4 and dedo != 0:
                flexion[:, vecino] += fuerza * azar.uniform(0.1, 0.4) * curva
        toques.append((reloj, dedo))
        reloj += azar.uniform(0.55, 1.3)

    # Cambios lentos de postura de un dedo (2-3 s), que no son toques.
    for inicio in np.arange(3.0, segundos - 4.0, 7.0) + azar.uniform(0, 2, len(np.arange(3.0, segundos - 4.0, 7.0))):
        duracion = azar.uniform(2.0, 3.0)
        flexion[:, int(azar.integers(1, 5))] += azar.uniform(0.25, 0.45) * _rampa(t, inicio, duracion / 2, 0.5, duracion / 2)
    # La muñeca se inclina hacia delante: dedos y palma se acortan a la vez.
    for inicio in np.arange(5.0, segundos - 2.0, 11.0):
        inclinacion += azar.uniform(0.15, 0.3) * _rampa(t, inicio, 0.25, 0.6, 0.3)
    # La mano se relaja o se cierra: los cuatro dedos se doblan juntos.
    for inicio in np.arange(9.0, segundos - 2.0, 13.0):
        flexion[:, 1:] += azar.uniform(0.45, 0.75) * _rampa(t, inicio, 0.2, 0.5, 0.3)[:, None]

    tam = 120 + 25 * np.sin(2 * np.pi * t / 23.0)  # se acerca y se aleja de la cámara
    flexion = np.clip(flexion, 0, 1)
    puntos = np.empty((len(t), 21, 2))
    for k in range(len(t)):
        p = mano_sintetica(cx[k], 470, tam[k], flexion[k])
        # Inclinar la mano acorta los dedos en vertical respecto a la muñeca.
        puntos[k] = p
        puntos[k, 1:, 1] = p[0, 1] + (p[1:, 1] - p[0, 1]) * (1 - inclinacion[k])
    return Sesion(t, puntos, tam, toques)


# ----------------------------------------------------------------- medición
@dataclass
class Resultado:
    precision: float
    sensibilidad: float
    f1: float
    latencia_ms: float
    falsos_por_minuto: float


@contextmanager
def ajustes(**valores) -> Iterator[None]:
    """Cambia temporalmente constantes de ``config`` (para el estudio de ablación)."""
    anteriores = {k: getattr(config, k) for k in valores}
    for k, v in valores.items():
        setattr(config, k, v)
    try:
        yield
    finally:
        for k, v in anteriores.items():
            setattr(config, k, v)


def medir(sesiones: Sequence[Sesion], umbral: float, ruido: float, semilla: int = 0) -> Resultado:
    azar = np.random.default_rng(semilla)
    aciertos = falsos = reales = 0
    latencias: List[float] = []
    minutos = 0.0
    for s in sesiones:
        detector = DetectorToques(umbral)
        detectados: List[Tuple[float, int]] = []
        temblor = azar.normal(0, 1, s.puntos.shape) * (ruido * s.tam)[:, None, None]
        for k, t in enumerate(s.tiempos):
            for toque in detector.actualizar([s.puntos[k] + temblor[k]], float(t)):
                if toque.pulsa:
                    detectados.append((float(t), toque.dedo))
        usados = set()
        for inicio, dedo in s.toques:
            for j, (t_det, d_det) in enumerate(detectados):
                if j not in usados and d_det == dedo and inicio <= t_det <= inicio + VENTANA:
                    usados.add(j)
                    latencias.append(t_det - inicio)
                    break
        aciertos += len(usados)
        falsos += len(detectados) - len(usados)
        reales += len(s.toques)
        minutos += s.tiempos[-1] / 60.0
    precision = aciertos / max(aciertos + falsos, 1)
    sensibilidad = aciertos / max(reales, 1)
    f1 = 2 * precision * sensibilidad / max(precision + sensibilidad, 1e-9)
    latencia = 1000 * float(np.mean(latencias)) if latencias else float("nan")
    return Resultado(precision, sensibilidad, f1, latencia, falsos / minutos)


# ------------------------------------------------------------------- gráfico
SUPERFICIE, TINTA, TINTA_2, REJILLA = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")  # paleta categórica validada (orden fijo)


def graficar(umbrales, por_umbral, ruidos, por_ruido, ablacion, destino: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
        "axes.edgecolor": REJILLA, "axes.labelcolor": TINTA_2, "axes.titlecolor": TINTA,
        "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "xtick.color": TINTA_2, "ytick.color": TINTA_2, "axes.grid": True, "grid.color": REJILLA,
        "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "legend.frameon": False,
    })
    figura, ejes = plt.subplots(2, 2, figsize=(12, 8.2))
    elegido = config.SENSIBILIDAD

    def lineas(eje, x, filas, nombres, rotular=True):
        marcas = ("o", "s", "^")
        for i, (nombre, valores) in enumerate(zip(nombres, filas)):
            eje.plot(x, valores, color=SERIES[i], lw=2, marker=marcas[i], ms=5, label=nombre)
            if rotular:
                eje.annotate(nombre, (x[-1], valores[-1]), xytext=(6, 0), textcoords="offset points",
                             va="center", color=TINTA_2, fontsize=9)

    eje = ejes[0, 0]
    filas = [[r.precision for r in por_umbral], [r.sensibilidad for r in por_umbral], [r.f1 for r in por_umbral]]
    lineas(eje, umbrales, filas, ("Precisión", "Sensibilidad", "F1"))
    eje.axvline(elegido, color=TINTA_2, lw=1, ls="--")
    eje.text(elegido, 0.02, " umbral elegido", color=TINTA_2, fontsize=9, transform=eje.get_xaxis_transform())
    eje.set(title="Calidad de la detección según el umbral", xlabel="Umbral (caída relativa del dedo)",
            ylabel="Proporción", ylim=(0, 1.05), xlim=(umbrales[0], umbrales[-1] + 0.06))
    eje.legend(loc="lower left", bbox_to_anchor=(0.0, 0.08))

    eje = ejes[0, 1]
    eje.plot(umbrales, [r.latencia_ms for r in por_umbral], color=SERIES[0], lw=2, marker="o", ms=5)
    eje.axvline(elegido, color=TINTA_2, lw=1, ls="--")
    eje.set(title="Latencia media del toque según el umbral", xlabel="Umbral (caída relativa del dedo)",
            ylabel="ms desde que el dedo empieza a bajar", ylim=(0, None))

    eje = ejes[1, 0]
    x = [100 * r for r in ruidos]
    filas = [[r.precision for r in por_ruido], [r.sensibilidad for r in por_ruido], [r.f1 for r in por_ruido]]
    # Las tres curvas casi coinciden: se rotulan con la leyenda y el eje se acerca.
    lineas(eje, x, filas, ("Precisión", "Sensibilidad", "F1"), rotular=False)
    eje.axvline(100 * RUIDO_BASE, color=TINTA_2, lw=1, ls="--")
    eje.text(100 * RUIDO_BASE, 0.02, " ruido supuesto", color=TINTA_2, fontsize=9,
             transform=eje.get_xaxis_transform())
    eje.set(title="Robustez frente al temblor de los puntos", xlabel="Ruido (% del tamaño de la mano)",
            ylabel="Proporción (eje desde 0,8)", ylim=(0.8, 1.0), xlim=(x[0], x[-1]))
    eje.legend(loc="lower left")

    eje = ejes[1, 1]
    nombres = list(ablacion)
    valores = [ablacion[n].falsos_por_minuto for n in nombres]
    barras = eje.barh(nombres[::-1], valores[::-1], color=SERIES[0], height=0.55)
    for barra, nombre in zip(barras, nombres[::-1]):
        r = ablacion[nombre]
        eje.text(barra.get_width() + max(valores) * 0.015, barra.get_y() + barra.get_height() / 2,
                 "%.1f /min · F1 %.2f" % (r.falsos_por_minuto, r.f1), va="center", color=TINTA, fontsize=9)
    eje.set(title="Ablación: notas fantasma al quitar cada mecanismo",
            xlabel="Notas fantasma por minuto (menos es mejor)", xlim=(0, max(valores) * 1.45))
    eje.grid(axis="y", visible=False)
    figura.tight_layout(pad=1.6)
    figura.savefig(destino, dpi=130)


# -------------------------------------------------------------------- informe
def tabla(filas: Sequence[Tuple[str, Resultado]], primera: str) -> str:
    lineas = ["| %s | Precisión | Sensibilidad | F1 | Latencia media | Falsos/min |" % primera,
              "|---|---:|---:|---:|---:|---:|"]
    for nombre, r in filas:
        lineas.append("| %s | %.3f | %.3f | %.3f | %.0f ms | %.1f |" % (
            nombre, r.precision, r.sensibilidad, r.f1, r.latencia_ms, r.falsos_por_minuto))
    return "\n".join(lineas)


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    argumentos.add_argument("--rapido", action="store_true", help="menos sesiones, para probar el script")
    argumentos.add_argument("--semilla", type=int, default=2026)
    args = argumentos.parse_args()

    inicio = time.perf_counter()
    azar = np.random.default_rng(args.semilla)
    sesiones = [generar_sesion(azar) for _ in range(2 if args.rapido else 6)]
    total_toques = sum(len(s.toques) for s in sesiones)
    print("%d sesiones de 60 s, %d toques reales" % (len(sesiones), total_toques))

    umbrales = np.round(np.arange(0.08, 0.405, 0.02), 2)
    por_umbral = [medir(sesiones, u, RUIDO_BASE) for u in umbrales]
    ruidos = (0.0, 0.004, 0.008, 0.012, 0.016, 0.02, 0.025)
    por_ruido = [medir(sesiones, config.SENSIBILIDAD, r) for r in ruidos]

    u = config.SENSIBILIDAD
    ablacion: Dict[str, Resultado] = {"Detector completo": medir(sesiones, u, RUIDO_BASE)}
    with ajustes(MODO_COMUN=False):
        ablacion["Sin rechazo de modo común"] = medir(sesiones, u, RUIDO_BASE)
    with ajustes(DOMINANCIA=0.0):
        ablacion["Sin filtro de dominancia"] = medir(sesiones, u, RUIDO_BASE)
    with ajustes(TAU_REPOSO=1e9):
        ablacion["Sin referencia adaptativa"] = medir(sesiones, u, RUIDO_BASE)
    with ajustes(CAMBIO_POSTURA=99):
        ablacion["Sin regla de cambio de postura"] = medir(sesiones, u, RUIDO_BASE)
    with ajustes(RAPIDEZ_MAX=1e9):
        ablacion["Sin bloqueo al desplazar la mano"] = medir(sesiones, u, RUIDO_BASE)
    with ajustes(SUAVIZADO=1.0):
        ablacion["Sin suavizado"] = medir(sesiones, u, RUIDO_BASE)

    # Elección conjunta de umbral y suavizado: calidad frente a latencia, con
    # ruido normal y con ruido alto (por si MediaPipe tiembla más de lo supuesto).
    rejilla = []
    for suavizado in (0.6, 0.8, 1.0):
        with ajustes(SUAVIZADO=suavizado):
            for umbral in (0.20, 0.22, 0.24):
                for ruido in (RUIDO_BASE, 0.025):
                    nombre = "%.1f · %.2f · %.1f %%" % (suavizado, umbral, 100 * ruido)
                    rejilla.append((nombre, medir(sesiones, umbral, ruido)))

    # ¿Y si la gente toca más suave de lo simulado? Mismas condiciones, toques más leves.
    azar_suave = np.random.default_rng(args.semilla)
    suaves = [generar_sesion(azar_suave, intensidad=(0.35, 0.7)) for _ in sesiones]
    por_umbral_suave = [(x, medir(suaves, x, RUIDO_BASE)) for x in (0.18, 0.20, 0.22, 0.24, 0.26)]

    docs = RAIZ / "docs"
    docs.mkdir(exist_ok=True)
    graficar(umbrales, por_umbral, ruidos, por_ruido, ablacion, docs / "evaluacion.png")

    mejor = max(zip(umbrales, por_umbral), key=lambda par: par[1].f1)
    texto = [
        "# Resultados de la evaluación del detector",
        "",
        "Generado por `scripts/evaluar_detector.py` (semilla %d): %d sesiones sintéticas de 60 s "
        "a %d fps con %d toques reales, más arrastres del dedo vecino, cambios lentos de postura, "
        "inclinaciones de la muñeca, cierres de la mano, desplazamientos entre teclas y cambios de distancia a la cámara. "
        "Ruido supuesto: %.1f %% del tamaño de la mano. Un toque cuenta como detectado si suena "
        "el dedo correcto en los %d ms siguientes a que empiece a bajar."
        % (args.semilla, len(sesiones), FPS, total_toques, 100 * RUIDO_BASE, 1000 * VENTANA),
        "",
        "![Evaluación](evaluacion.png)",
        "",
        "## Según el umbral",
        "",
        tabla([("%.2f%s" % (x, " (elegido)" if abs(x - u) < 1e-9 else ""), r)
               for x, r in zip(umbrales, por_umbral)], "Umbral"),
        "",
        "Mejor F1 en este barrido: umbral %.2f (F1 = %.3f)." % (mejor[0], mejor[1].f1),
        "",
        "## Según el ruido de los puntos (umbral %.2f)" % u,
        "",
        tabla([("%.1f %%" % (100 * r), res) for r, res in zip(ruidos, por_ruido)], "Ruido"),
        "",
        "## Elección de umbral y suavizado",
        "",
        "Suavizado = peso de la medida nueva en el filtro exponencial (1.0 = sin suavizar). "
        "Valores actuales: suavizado %.1f, umbral %.2f." % (config.SUAVIZADO, u),
        "",
        tabla(rejilla, "Suavizado · umbral · ruido"),
        "",
        "## Con toques más suaves",
        "",
        "Las mismas sesiones, pero con toques que doblan el dedo entre un 35 % y un 70 % "
        "(en lugar de 55 %-100 %), como haría alguien que toca con timidez.",
        "",
        tabla([("%.2f%s" % (x, " (elegido)" if abs(x - u) < 1e-9 else ""), r) for x, r in por_umbral_suave], "Umbral"),
        "",
        "## Ablación (umbral %.2f, ruido %.1f %%)" % (u, 100 * RUIDO_BASE),
        "",
        tabla(list(ablacion.items()), "Variante"),
        "",
        "> Son datos **sintéticos**: sirven para comparar variantes del detector y elegir "
        "parámetros de forma razonada, no para afirmar cómo se comportará con cualquier mano real.",
        "",
    ]
    (docs / "RESULTADOS_EVALUACION.md").write_text("\n".join(texto), encoding="utf-8")
    print("\n".join(texto[10:]))
    print("Listo en %.0f s: docs/evaluacion.png y docs/RESULTADOS_EVALUACION.md" % (time.perf_counter() - inicio))


if __name__ == "__main__":
    main()
