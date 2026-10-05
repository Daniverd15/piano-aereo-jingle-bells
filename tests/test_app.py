"""Prueba de extremo a extremo sin cámara ni altavoces: mano simulada -> nota -> pantalla."""

import numpy as np

from piano_aereo import config
from piano_aereo.app import App, crear_argumentos
from piano_aereo.simulacion import mano_sintetica

DT = 1 / 30.0


def crear(*extra):
    return App(crear_argumentos().parse_args(["--sin-camara", "--sin-sonido"] + list(extra)))


def tocar_con_indice(app, tecla, t):
    """Lleva el índice de una mano simulada al carril de la tecla y lo dobla."""
    x_punta = mano_sintetica(0, 0)[8][0]
    cx = app.teclado.centro(tecla) - x_punta
    for flexion, cuadros in (((0, 0, 0, 0, 0), 12), ((0, 1, 0, 0, 0), 5), ((0, 0, 0, 0, 0), 6)):
        for _ in range(cuadros):
            t += DT
            app.procesar_manos([mano_sintetica(cx, 480, flexion=flexion)], t)
            app.avanzar(t, DT)
    return t


def test_tocar_el_coro_completo_con_la_mano_simulada():
    app = crear("--modo", "guia")
    t = 0.0
    for nota in app.cancion.notas:
        assert app.guia.objetivo == nota.nota
        t = tocar_con_indice(app, app.teclado.indice(nota.nota), t)
    assert app.guia.terminada and app.guia.errores == 0
    assert app.guia.aciertos == len(app.cancion)
    assert not app.pulsadas
    lienzo = app.componer(t)
    assert lienzo.shape == (config.ALTO, config.ANCHO, 3) and lienzo.dtype == np.uint8


def test_una_nota_equivocada_cuenta_como_error():
    app = crear("--modo", "guia")
    tocar_con_indice(app, app.teclado.indice("C4"), 0.0)
    assert (app.guia.errores, app.guia.indice) == (1, 0)


def test_todos_los_modos_y_teclas_se_dibujan():
    app = crear()
    t = 1.0
    for tecla in "123strhe+-zm/":
        assert app.tecla_pc(ord(tecla), t)
        for _ in range(3):
            t += DT
            app.avanzar(t, DT)
            app.componer(t)
    assert app.tecla_pc(ord("3"), t) and app.modo == "demo"
    for _ in range(200):
        t += DT
        app.avanzar(t, DT)
    assert app.demo.indice > 5
    assert not app.tecla_pc(ord("Q"), t) and not app.tecla_pc(27, t)
