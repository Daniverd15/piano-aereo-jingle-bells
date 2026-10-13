"""Pruebas de extremo a extremo sin cámara ni altavoces: mano simulada -> nota -> pantalla."""

import numpy as np

from piano_aereo import config
from piano_aereo.app import App, crear_argumentos
from piano_aereo.simulacion import mano_sintetica

DT = 1 / 30.0
ABIERTA = (0, 0, 0, 0, 0)
INDICE = (0, 1, 0, 0, 0)
X_INDICE = mano_sintetica(0, 0)[8][0]


def crear(*extra):
    return App(crear_argumentos().parse_args(["--sin-camara", "--sin-sonido"] + list(extra)))


def cuadro(app, t, x, flexion):
    """Un fotograma: la punta del índice de la mano simulada está en ``x``."""
    app.procesar_manos([mano_sintetica(x - X_INDICE, 480, flexion=flexion)], t)
    app.avanzar(t, DT)


def tocar_con_indice(app, tecla, t, x=None):
    """Lleva el índice al carril de la tecla (o a ``x``) y lo dobla."""
    x = app.teclado.centro(tecla) if x is None else x
    for flexion, cuadros in ((ABIERTA, 12), (INDICE, 5), (ABIERTA, 6)):
        for _ in range(cuadros):
            t += DT
            cuadro(app, t, x, flexion)
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


def test_la_asistencia_perdona_un_toque_al_borde_de_la_tecla():
    mi = 5  # la primera nota del coro es Mi (E4)
    for extra, esperado in (((), (1, 0)), (("--sin-asistencia",), (0, 1))):
        app = crear("--modo", "guia", *extra)
        x0, _, _, _ = app.teclado.rect(mi)
        tocar_con_indice(app, mi, 0.0, x=x0 - 20)  # cae 20 px dentro de la tecla vecina (Re)
        assert (app.guia.aciertos, app.guia.errores) == esperado
    # Lejos del borde no hay perdón: es otra tecla.
    app = crear("--modo", "guia")
    tocar_con_indice(app, mi, 0.0, x=app.teclado.centro(mi - 1))
    assert (app.guia.aciertos, app.guia.errores) == (0, 1)


def test_modo_ritmo_tocado_a_tiempo_con_la_mano_simulada():
    """La mano simulada toca cada nota en su instante: todo acierta y nada falla."""
    app = crear("--modo", "ritmo", "--dificultad", "facil")
    app.cambiar_modo("ritmo", 0.0)
    ritmo, notas = app.ritmo, app.cancion.notas
    t, siguiente, flexion, x = 0.0, 0, ABIERTA, app.teclado.centro(5)
    doblado_hasta = -1.0
    while not ritmo.terminada(t):
        t += DT
        if siguiente < len(notas):
            x = app.teclado.centro(app.teclado.indice(notas[siguiente].nota))
            # El detector necesita un par de fotogramas para ver el dedo doblado.
            if t >= ritmo.instante(siguiente) - 0.02:
                doblado_hasta, siguiente = t + 3 * DT, siguiente + 1
        flexion = INDICE if t <= doblado_hasta else ABIERTA
        cuadro(app, t, x, flexion)
        if int(t / DT) % 15 == 0:
            app.componer(t)
    assert ritmo.conteo["fallo"] == 0
    assert ritmo.aciertos == len(notas) and ritmo.mejor_combo == len(notas)
    assert ritmo.multiplicador == 4 and ritmo.calificacion in ("S", "A")
    assert ritmo.puntos > 100 * len(notas)  # el combo multiplica
    app.componer(t)  # panel de resultados


def test_modo_ritmo_sin_tocar_falla_todo():
    app = crear("--modo", "ritmo", "--dificultad", "dificil")
    app.cambiar_modo("ritmo", 0.0)
    t = 0.0
    while not app.ritmo.terminada(t):
        t += DT
        app.avanzar(t, DT)
    assert app.ritmo.conteo == {"perfecto": 0, "bien": 0, "fallo": len(app.cancion)}
    assert app.ritmo.puntos == 0 and app.ritmo.calificacion == "D" and app.ritmo.estrellas == 1


def test_todos_los_modos_y_teclas_se_dibujan():
    app = crear()
    t = 1.0
    for tecla in "1234sdtparhhe+-zm/":
        assert app.tecla_pc(ord(tecla), t)
        for _ in range(3):
            t += DT
            app.avanzar(t, DT)
            app.componer(t)
    assert app.tecla_pc(ord("4"), t) and app.modo == "demo"
    for _ in range(300):
        t += DT
        app.avanzar(t, DT)
        app.componer(t) if _ % 30 == 0 else None
    assert app.demo.indice > 5
    assert not app.tecla_pc(ord("Q"), t) and not app.tecla_pc(27, t)


def test_la_demo_se_repite_al_terminar():
    app = crear("--modo", "demo", "--dificultad", "dificil")
    app.cambiar_modo("demo", 0.0)
    t, vueltas, anterior = 0.0, 0, 0
    for _ in range(int(80 / DT)):
        t += DT
        app.avanzar(t, DT)
        vueltas += app.demo.indice < anterior
        anterior = app.demo.indice
    assert vueltas >= 1 and not [v for v in app.pulsadas if v[1] >= len(app.cancion)]
