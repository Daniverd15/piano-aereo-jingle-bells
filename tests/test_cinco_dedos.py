"""Forma de tocar «cinco dedos»: cada dedo recibe una tecla según dónde está la mano."""

import time

import cv2
import numpy as np

from piano_aereo import config
from piano_aereo.app import App, crear_argumentos
from piano_aereo.asignacion import CincoDedos
from piano_aereo.notas import Teclado
from piano_aereo.simulacion import mano_sintetica
from piano_aereo.toques import Lectura

DT = 1 / 30.0
ABIERTA = (0, 0, 0, 0, 0)
DO, RE, MI, FA, SOL = 3, 4, 5, 6, 7  # índices de las teclas en el teclado de Sol3 a Si4


def teclado():
    return Teclado(config.NOTAS_TECLADO, config.TECLADO_MARGEN, config.TECLADO_Y,
                   config.ANCHO - 2 * config.TECLADO_MARGEN, config.TECLADO_ALTO)


def lecturas(xs, lado="der", pulsado=()):
    return [Lectura(lado, d, (x, 300.0), x, 0.0, d in pulsado) for d, x in enumerate(xs)]


def dedos_en(t, centro_tecla, separacion=40.0):
    """Cinco puntas alrededor del centro de una tecla, de izquierda a derecha."""
    c = t.centro(centro_tecla)
    return [c + (k - 2) * separacion for k in range(5)]


def test_la_tecla_central_queda_bajo_el_centro_de_la_mano():
    t = teclado()
    cinco = CincoDedos(t)
    cinco.actualizar(lecturas(dedos_en(t, MI)))
    assert [cinco.tecla("der", d) for d in range(5)] == [DO, RE, MI, FA, SOL]
    assert cinco.dedo_para(SOL) == ("der", 4) and cinco.dedo_para(0) is None


def test_los_dedos_se_ordenan_por_pantalla_sin_importar_que_mano_es():
    t = teclado()
    cinco = CincoDedos(t)
    # Mano vista al revés: el pulgar (dedo 0) es el de más a la derecha.
    cinco.actualizar(lecturas(dedos_en(t, MI)[::-1], lado="izq"))
    assert [cinco.tecla("izq", d) for d in range(5)] == [SOL, FA, MI, RE, DO]


def test_histeresis_y_desplazamiento():
    t = teclado()
    cinco = CincoDedos(t)
    cinco.actualizar(lecturas(dedos_en(t, MI)))
    ancho = t.ancho_tecla
    # Un poco más allá del borde de la tecla central: no se mueve (no parpadea).
    cinco.actualizar(lecturas([x + 0.7 * ancho for x in dedos_en(t, MI)]))
    assert cinco.tecla("der", 0) == DO
    # Una tecla entera más allá: la posición se desplaza una tecla.
    cinco.actualizar(lecturas([x + 1.0 * ancho for x in dedos_en(t, MI)]))
    assert cinco.tecla("der", 0) == RE
    # En los extremos la posición se queda dentro del teclado.
    cinco.actualizar(lecturas(dedos_en(t, 0)))
    assert [cinco.tecla("der", d) for d in range(5)] == [0, 1, 2, 3, 4]
    cinco.actualizar(lecturas(dedos_en(t, 9)))
    assert cinco.tecla("der", 4) == 9


def test_con_un_dedo_pulsado_la_posicion_no_se_mueve():
    t = teclado()
    cinco = CincoDedos(t)
    cinco.actualizar(lecturas(dedos_en(t, MI)))
    cinco.actualizar(lecturas(dedos_en(t, 8), pulsado=(2,)))
    assert cinco.tecla("der", 0) == DO
    cinco.actualizar(lecturas(dedos_en(t, 7)))  # al soltar, ya se desplaza
    assert cinco.tecla("der", 0) == MI
    cinco.actualizar([])  # la mano sale de la imagen
    assert cinco.teclas() == {}


# ------------------------------------------------------------ de extremo a extremo
def crear(*extra):
    return App(crear_argumentos().parse_args(["--sin-camara", "--sin-sonido", "--cinco-dedos"] + list(extra)))


def centro_para(app, tecla_central):
    """Posición de la muñeca para que la mano simulada quede centrada sobre esa tecla."""
    p = mano_sintetica(0, 0)
    return app.teclado.centro(tecla_central) - float(np.median(p[[4, 8, 12, 16, 20], 0]))


def test_el_coro_entero_sin_mover_la_mano():
    app = crear("--modo", "guia")
    cx, t = centro_para(app, MI), 0.0
    for _ in range(15):
        t += DT
        app.procesar_manos([mano_sintetica(cx, 480)], t)
    dedo_de = {app.cinco.tecla("der", d): d for d in range(5)}
    assert sorted(dedo_de) == [DO, RE, MI, FA, SOL]
    for nota in app.cancion.notas:
        dedo = dedo_de[app.teclado.indice(nota.nota)]
        assert app._siguiente_tecla() == app.teclado.indice(nota.nota)
        assert app.cinco.dedo_para(app._siguiente_tecla()) == ("der", dedo)
        flexion = [0.0] * 5
        flexion[dedo] = 1.0
        for f, cuadros in ((flexion, 5), (ABIERTA, 8)):
            for _ in range(cuadros):
                t += DT
                app.procesar_manos([mano_sintetica(cx, 480, flexion=f)], t)
                app.avanzar(t, DT)
    assert app.guia.terminada and app.guia.errores == 0
    assert app.guia.aciertos == len(app.cancion)


def test_cambiar_de_forma_de_tocar_con_la_tecla_5(monkeypatch):
    app = crear("--modo", "guia")
    cx, t = centro_para(app, MI), 0.0
    for _ in range(15):
        t += DT
        app.procesar_manos([mano_sintetica(cx, 480)], t)
    monkeypatch.setattr(cv2, "imshow", lambda *a: None)
    assert app.cinco_dedos
    app._paso(time.perf_counter())  # dibuja números de dedo y el dedo resaltado sin errores
    assert app._errores == 0
    app.tecla_pc(ord("5"), t)
    assert not app.cinco_dedos and "apuntar" in app._aviso[0]
    app._paso(time.perf_counter())
    app.tecla_pc(ord("5"), t)
    assert app.cinco_dedos and app._errores == 0
