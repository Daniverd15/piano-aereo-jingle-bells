"""Analiza los datos de interpretaciones reales guardados en ``grabaciones/datos_*.csv``.

Cada vez que se termina una canción en los modos Guía o Ritmo, la aplicación
guarda un CSV con una fila por nota tocada. Este script los lee y responde:

- ¿Qué proporción de las notas fueron correctas, en total y por dedo?
- En el modo Ritmo, ¿se toca a tiempo, tarde o temprano? ¿Con cuánta dispersión?
- ¿Mejora la puntería de una sesión a la siguiente?

    python scripts/analizar_sesion.py                 (todas las sesiones de grabaciones/)
    python scripts/analizar_sesion.py archivo.csv ... (sesiones concretas)

Genera ``grabaciones/analisis.png``. Requiere matplotlib
(``python -m pip install -r requirements-dev.txt``).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
DEDOS = ("pulgar", "índice", "medio", "anular", "meñique")
CORRECTAS = {"acierto", "perfecto", "bien"}
INCORRECTAS = {"error", "sobra"}

SUPERFICIE, TINTA, TINTA_2, REJILLA = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIE = "#2a78d6"


def leer(rutas: Sequence[Path]) -> List[Dict[str, str]]:
    filas = []
    for ruta in sorted(rutas):
        with open(ruta, encoding="utf-8-sig", newline="") as archivo:
            for fila in csv.DictReader(archivo):
                fila["sesion"] = ruta.stem
                filas.append(fila)
    return filas


def resumir(filas: List[Dict[str, str]]) -> Dict[str, object]:
    """Indicadores principales de un conjunto de notas tocadas."""
    juzgadas = [f for f in filas if f["resultado"] in CORRECTAS | INCORRECTAS]
    correctas = [f for f in juzgadas if f["resultado"] in CORRECTAS]
    por_dedo = {}
    for dedo in DEDOS:
        del_dedo = [f for f in juzgadas if f["dedo"] == dedo]
        if del_dedo:
            aciertos = sum(f["resultado"] in CORRECTAS for f in del_dedo)
            por_dedo[dedo] = (aciertos, len(del_dedo))
    desfases = np.array([float(f["desfase_ms"]) for f in filas if f.get("desfase_ms")], dtype=float)
    por_sesion = []
    for sesion in sorted({f["sesion"] for f in filas}):
        de_sesion = [float(f["desfase_ms"]) for f in filas if f["sesion"] == sesion and f.get("desfase_ms")]
        if de_sesion:
            por_sesion.append((sesion, float(np.mean(np.abs(de_sesion)))))
    return {
        "notas": len(filas),
        "juzgadas": len(juzgadas),
        "acierto": len(correctas) / len(juzgadas) if juzgadas else float("nan"),
        "por_dedo": por_dedo,
        "desfases": desfases,
        "por_sesion": por_sesion,
    }


def informe(resumen: Dict[str, object]) -> str:
    lineas = ["Notas tocadas: %d (con nota esperada: %d)" % (resumen["notas"], resumen["juzgadas"])]
    if resumen["juzgadas"]:
        lineas.append("Proporción de notas correctas: %.1f %%" % (100 * resumen["acierto"]))
    for dedo, (aciertos, total) in resumen["por_dedo"].items():
        lineas.append("  %-8s %3d/%-3d correctas (%.0f %%)" % (dedo, aciertos, total, 100 * aciertos / total))
    d = resumen["desfases"]
    if len(d):
        lineas.append("Modo Ritmo, %d notas acertadas: desfase medio %+.0f ms, mediana %+.0f ms, "
                      "desviación típica %.0f ms (positivo = tarde)" % (len(d), d.mean(), np.median(d), d.std()))
    return "\n".join(lineas)


def graficar(resumen: Dict[str, object], destino: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10, "axes.edgecolor": REJILLA,
        "axes.labelcolor": TINTA_2, "axes.titlecolor": TINTA, "axes.titlesize": 11.5,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "xtick.color": TINTA_2,
        "ytick.color": TINTA_2, "axes.grid": True, "grid.color": REJILLA, "axes.spines.top": False,
        "axes.spines.right": False, "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE,
    })
    figura, ejes = plt.subplots(1, 3, figsize=(15, 4.4))

    eje = ejes[0]
    d = resumen["desfases"]
    if len(d):
        eje.hist(d, bins=np.arange(-280, 281, 20), color=SERIE, edgecolor=SUPERFICIE, linewidth=2)
        eje.axvline(0, color=TINTA_2, lw=1)
        eje.axvline(float(np.median(d)), color=TINTA, lw=1.5, ls="--")
        eje.text(float(np.median(d)), eje.get_ylim()[1] * 0.95, "  mediana %+.0f ms" % np.median(d),
                 color=TINTA, fontsize=9, va="top",
                 bbox=dict(facecolor=SUPERFICIE, edgecolor="none", pad=1.5))
    else:
        eje.text(0.5, 0.5, "Sin datos del modo Ritmo", ha="center", transform=eje.transAxes, color=TINTA_2)
    eje.set(title="¿Tarde o temprano? (modo Ritmo)", xlabel="Desfase (ms, positivo = tarde)",
            ylabel="Notas")

    eje = ejes[1]
    dedos = list(resumen["por_dedo"])
    if dedos:
        tasas = [100 * a / t for a, t in resumen["por_dedo"].values()]
        barras = eje.bar(dedos, tasas, color=SERIE, width=0.6)
        for barra, (a, t) in zip(barras, resumen["por_dedo"].values()):
            eje.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + 1.5, "%d/%d" % (a, t),
                     ha="center", color=TINTA, fontsize=9)
    eje.set(title="Notas correctas por dedo", ylabel="% correctas", ylim=(0, 112))
    eje.grid(axis="x", visible=False)

    eje = ejes[2]
    sesiones = resumen["por_sesion"]
    if sesiones:
        eje.plot(range(1, len(sesiones) + 1), [m for _, m in sesiones], color=SERIE, lw=2, marker="o", ms=6)
        eje.set_xticks(range(1, len(sesiones) + 1))
    else:
        eje.text(0.5, 0.5, "Sin datos del modo Ritmo", ha="center", transform=eje.transAxes, color=TINTA_2)
    eje.set(title="Evolución entre sesiones", xlabel="Sesión (orden cronológico)",
            ylabel="Error medio absoluto (ms)", ylim=(0, None))
    figura.tight_layout(pad=1.6)
    figura.savefig(destino, dpi=120)


def main(argv: Sequence[str] = None) -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    argumentos.add_argument("csv", nargs="*", type=Path, help="CSV concretos (por defecto, todos los de grabaciones/)")
    argumentos.add_argument("--salida", type=Path, default=RAIZ / "grabaciones" / "analisis.png")
    args = argumentos.parse_args(argv)
    rutas = args.csv or sorted((RAIZ / "grabaciones").glob("datos_*.csv"))
    if not rutas:
        print("No hay datos todavía: termina una canción en el modo Guía (2) o Ritmo (3).")
        return 1
    resumen = resumir(leer(rutas))
    print("%d sesión(es)\n%s" % (len(rutas), informe(resumen)))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    graficar(resumen, args.salida)
    print("Gráfico guardado en %s" % args.salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
