"""Espectro, datos de sesión, calibración, ajustes guardados, gesto de puño y celebración."""

import csv
import json
import time

import cv2
import numpy as np
import pytest

from piano_aereo import ajustes, config, sesion
from piano_aereo.app import App, completar_argumentos, crear_argumentos
from piano_aereo.espectro import analizar, nombre_nota
from piano_aereo.gestos import GestoPuno, es_puno
from piano_aereo.sesion import Sesion, correccion_sugerida, describir_desfase
from piano_aereo.simulacion import mano_sintetica

DT = 1 / 30.0


def crear(*extra, guardados=None):
    return App(crear_argumentos().parse_args(["--sin-camara", "--sin-sonido"] + list(extra)), guardados)


def puno(cx=640.0, cy=480.0):
    """Mano cerrada: cada punta vuelve hacia la palma, por debajo de su articulación media."""
    p = mano_sintetica(cx, cy)
    for punta, nudillo in ((8, 5), (12, 9), (16, 13), (20, 17)):
        p[punta] = p[0] + 0.5 * (p[nudillo] - p[0])
    return p


# ------------------------------------------------------------------ espectro
@pytest.mark.parametrize("frecuencia, nota", [(440.0, "La4"), (261.63, "Do4"), (196.0, "Sol3")])
def test_el_espectro_reconoce_la_nota(frecuencia, nota):
    fm = 48000
    t = np.arange(4096) / fm
    onda = 0.3 * np.sin(2 * np.pi * frecuencia * t) + 0.08 * np.sin(2 * np.pi * 2 * frecuencia * t)
    niveles, pico = analizar(onda.astype(np.float32), fm)
    assert pico is not None and pico[1] == nota and abs(pico[0] - frecuencia) < 2.0
    assert niveles.shape == (56,) and niveles.max() > 0.7


def test_el_espectro_del_silencio_no_inventa_notas():
    niveles, pico = analizar(np.zeros(4096, np.float32), 48000)
    assert pico is None and not niveles.any()


def test_nombre_de_nota_y_centesimas():
    assert nombre_nota(440.0) == ("La4", 0)
    assert nombre_nota(440.0 * 2 ** (0.3 / 12)) == ("La4", 30)
    assert nombre_nota(466.16)[0] == "La#4"


# ---------------------------------------------------------------- sesión CSV
def test_guardar_la_sesion_en_csv(carpetas_temporales):
    s = Sesion()
    s.reiniciar(10.0)
    s.anotar(10.5, modo="ritmo", forma="apuntar", mano="der", dedo="índice", nota_tocada="E4",
             nota_esperada="E4", resultado="perfecto", desfase_ms=-12.5, fuerza=0.9)
    s.anotar(11.25, modo="ritmo", forma="apuntar", mano="der", dedo="índice", nota_tocada="F4",
             nota_esperada="", resultado="sobra", desfase_ms=None, fuerza=0.6)
    ruta = s.guardar("Jingle Bells (coro)")
    assert ruta.parent == carpetas_temporales / "grabaciones" and ruta.name.endswith("_ritmo.csv")
    with open(ruta, encoding="utf-8-sig") as archivo:
        filas = list(csv.DictReader(archivo))
    assert [f["segundo"] for f in filas] == ["0.5", "1.25"]
    assert filas[0]["dedo"] == "índice" and filas[0]["desfase_ms"] == "-12.5"
    assert filas[1]["resultado"] == "sobra" and filas[1]["desfase_ms"] == ""


def test_correccion_de_retraso():
    assert correccion_sugerida([0.06] * 9) is None  # pocas notas
    assert correccion_sugerida([0.01, -0.01, 0.015] * 5) is None  # ya va a tiempo
    tarde = [0.05, 0.06, 0.055, 0.045, 0.3, 0.05, 0.06, 0.052, 0.058, 0.049]
    assert correccion_sugerida(tarde) == pytest.approx(0.0535)  # la mediana ignora el 0.3
    assert correccion_sugerida([-0.04] * 12) == pytest.approx(-0.04)
    assert describir_desfase(tarde) == "En general tocas 54 ms tarde"
    assert describir_desfase([-0.04] * 12) == "En general tocas 40 ms temprano"
    assert describir_desfase([0.004] * 3).startswith("Tocas a tiempo")
    assert describir_desfase([]) == "Sin notas acertadas"


# ------------------------------------------------------------------- ajustes
def test_ajustes_se_guardan_y_se_validan(carpetas_temporales):
    ajustes.guardar({"sensibilidad": 0.3, "timbre": "campanas", "cinco_dedos": True, "retraso_camara": 0.09})
    assert ajustes.cargar() == {"sensibilidad": 0.3, "timbre": "campanas", "cinco_dedos": True,
                                "retraso_camara": 0.09}
    ajustes.RUTA.write_text(json.dumps({"sensibilidad": 7, "timbre": "tuba", "dificultad": "facil", "x": 1}))
    assert ajustes.cargar() == {"dificultad": "facil"}  # lo inválido se descarta
    ajustes.RUTA.write_text("{esto no es json")
    assert ajustes.cargar() == {}


def test_la_linea_de_ordenes_manda_sobre_lo_guardado():
    guardados = {"timbre": "campanas", "dificultad": "dificil", "sensibilidad": 0.3,
                 "cinco_dedos": True, "asistencia": False, "retraso_camara": 0.08}
    args = completar_argumentos(crear_argumentos().parse_args(["--timbre", "piano"]), guardados)
    assert (args.timbre, args.dificultad, args.sensibilidad) == ("piano", "dificil", 0.3)
    assert args.cinco_dedos and args.sin_asistencia and not args.sin_acompanamiento
    assert args.retraso_camara == 0.08
    de_fabrica = completar_argumentos(crear_argumentos().parse_args([]), {})
    assert (de_fabrica.timbre, de_fabrica.dificultad, de_fabrica.sensibilidad) == ("piano", "normal",
                                                                                    config.SENSIBILIDAD)
    app = crear(guardados=guardados)
    assert app.cinco_dedos and app.retraso_camara == 0.08 and app.ajustes_recuperados
    assert app.ajustes_actuales()["timbre"] == "campanas"


# ------------------------------------------------------------------- puño
def test_reconocer_el_puno():
    assert es_puno(puno()) and not es_puno(mano_sintetica(640, 480))
    gesto, t = GestoPuno(), 0.0
    disparos = 0
    for _ in range(int(1.6 / DT)):
        t += DT
        disparos += gesto.actualizar([puno()], t)[1]
    assert disparos == 1  # una sola vez aunque se mantenga cerrado
    gesto.actualizar([mano_sintetica(640, 480)], t + DT)  # al abrir la mano se rearma
    progreso = 0.0
    for k in range(10):
        progreso = gesto.actualizar([puno()], t + (k + 2) * DT)[0]
    assert 0.2 < progreso < 0.4


def test_el_puno_no_suena_ni_reinicia_en_mitad_de_la_cancion():
    app = crear("--modo", "guia")
    t = 0.0
    for mano, cuadros in ((mano_sintetica(640, 480), 15), (puno(), 60)):
        for _ in range(cuadros):
            t += DT
            app.procesar_manos([mano], t)
    assert not app.pulsadas and app.guia.errores == 0 and app._progreso_puno == 0.0


def test_el_puno_repite_la_cancion_en_los_resultados(monkeypatch):
    app = crear("--modo", "guia")
    for nota in app.cancion.notas:
        app.guia.pulsar(nota.nota, 1.0)
    assert app.en_resultados(1.0)
    t = 1.0
    for _ in range(int(1.2 / DT)):
        t += DT
        app.procesar_manos([puno()], t)
    assert app.guia.indice == 0 and not app.en_resultados(t) and "puño" in app._aviso[0]


# ------------------------------------------------- celebración y calibración
def tocar_ritmo_con_retraso(app, desfase):
    """Acierta todas las notas del modo Ritmo con el mismo desfase (s)."""
    ritmo = app.ritmo
    for i, nota in enumerate(app.cancion.notas):
        tecla = app.teclado.indice(nota.nota)
        t = ritmo.instante(i) + desfase
        app.tocar(("der", 1), tecla, 0.9, t, t)
        app.soltar(("der", 1))
        app.avanzar(t, DT)
    fin = ritmo.instante(len(app.cancion) - 1) + 3.0
    app.avanzar(fin, DT)
    return fin


def test_al_terminar_se_celebra_y_se_guardan_los_datos(carpetas_temporales, monkeypatch):
    app = crear("--modo", "ritmo")
    app.cambiar_modo("ritmo", 0.0)
    fin = tocar_ritmo_con_retraso(app, 0.0)
    assert app.ritmo.terminada(fin) and app._celebrado and app.fuegos.activos
    datos = list((carpetas_temporales / "grabaciones").glob("datos_*_ritmo.csv"))
    assert len(datos) == 1 and "Datos" in app._aviso[0]
    with open(datos[0], encoding="utf-8-sig") as archivo:
        filas = list(csv.DictReader(archivo))
    assert len(filas) == len(app.cancion) and {f["resultado"] for f in filas} == {"perfecto"}
    for _ in range(40):  # la fanfarria suena y se vacía; los fuegos se dibujan sin errores
        fin += DT
        app.avanzar(fin, DT)
        app.componer(fin)
    assert not app._fanfarria


def test_calibrar_el_retraso_tras_el_modo_ritmo(carpetas_temporales):
    app = crear("--modo", "ritmo")
    app.calibrar(0.0)
    assert "al terminar" in app._aviso[0]  # todavía no hay resultados
    app.cambiar_modo("ritmo", 0.0)
    fin = tocar_ritmo_con_retraso(app, 0.07)  # siempre 70 ms tarde
    assert correccion_sugerida(app.ritmo.desfases.values()) == pytest.approx(0.07)
    app.calibrar(fin)
    assert app.retraso_camara == pytest.approx(config.RETRASO_CAMARA + 0.07)
    assert ajustes.cargar()["retraso_camara"] == pytest.approx(0.12)
    assert correccion_sugerida(app.ritmo.desfases.values()) is None  # ya centrado
    app.calibrar(fin)
    assert "No hace falta" in app._aviso[0]


def test_espectro_arbol_y_ayuda_se_dibujan(monkeypatch):
    app = crear("--modo", "ritmo")
    monkeypatch.setattr(cv2, "imshow", lambda *a: None)
    for tecla in "oh":
        app.tecla_pc(ord(tecla), 1.0)
    assert app.ver_espectro and app.ver_ayuda
    anterior = time.perf_counter()
    for _ in range(5):
        anterior = app._paso(anterior)
    assert app._errores == 0
    # Con audio "disponible" el panel analiza las muestras recientes del mezclador.
    app.audio.disponible = True
    app.audio.tocar("x", "A4", 1.0)
    for _ in range(4):
        app.audio.mezclar(1024)
    app._paso(anterior)
    assert app._errores == 0


def test_analizar_las_sesiones_guardadas(carpetas_temporales):
    """De extremo a extremo: tocar en Ritmo -> CSV -> análisis con gráfico."""
    pytest.importorskip("matplotlib")
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import analizar_sesion

    for desfase in (0.08, 0.03):  # dos sesiones: la segunda, más a tiempo
        app = crear("--modo", "ritmo")
        app.cambiar_modo("ritmo", 0.0)
        tocar_ritmo_con_retraso(app, desfase)
        time.sleep(1.05)  # los CSV llevan la hora en el nombre
    rutas = sorted((carpetas_temporales / "grabaciones").glob("datos_*.csv"))
    resumen = analizar_sesion.resumir(analizar_sesion.leer(rutas))
    total = 2 * len(app.cancion)
    assert resumen["notas"] == total and resumen["acierto"] == 1.0
    assert resumen["por_dedo"] == {"índice": (total, total)}
    assert [round(m) for _, m in resumen["por_sesion"]] == [80, 30]
    assert "desfase medio +55 ms" in analizar_sesion.informe(resumen)
    salida = carpetas_temporales / "analisis.png"
    assert analizar_sesion.main([str(r) for r in rutas] + ["--salida", str(salida)]) == 0
    assert salida.stat().st_size > 10000
