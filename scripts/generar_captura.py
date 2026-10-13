"""Genera las capturas de ``docs/`` con manos simuladas.

No usa la cámara: las manos son sintéticas, por eso el fondo es un degradado.

    python scripts/generar_captura.py
"""

import sys
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from piano_aereo.app import App, crear_argumentos  # noqa: E402
from piano_aereo.simulacion import mano_sintetica  # noqa: E402

DT = 1 / 30.0
TAM = 105
X_INDICE = mano_sintetica(0, 0, tam=TAM)[8][0]
IZQUIERDA = mano_sintetica(215, 470, tam=TAM, derecha=False)
ABIERTA, INDICE = (0, 0, 0, 0, 0), (0, 1, 0, 0, 0)


def crear(modo):
    args = ["--sin-camara", "--sin-sonido", "--modo", modo, "--dificultad", "facil"]
    app = App(crear_argumentos().parse_args(args))
    app.cambiar_modo(modo, 0.0)
    return app


def cuadro(app, t, tecla, flexion):
    cx = app.teclado.centro(tecla) - X_INDICE
    app.procesar_manos([IZQUIERDA, mano_sintetica(cx, 470, tam=TAM, flexion=flexion)], t)
    app.avanzar(t, DT)
    return app.componer(t)


def guardar(nombre, lienzo):
    destino = RAIZ / "docs" / nombre
    destino.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(destino), lienzo)
    print("Guardada", destino)


def captura_guia():
    """Toca las ocho primeras notas y deja el dedo pulsando la novena."""
    app, t = crear("guia"), 0.0
    for n, nota in enumerate(app.cancion.notas[:9]):
        tecla = app.teclado.indice(nota.nota)
        for flexion, cuadros in ((ABIERTA, 12), (INDICE, 4), (ABIERTA, 6 if n < 8 else 0)):
            for _ in range(cuadros):
                t += DT
                lienzo = cuadro(app, t, tecla, flexion)
    guardar("captura.png", lienzo)


def captura_ritmo():
    """Toca a tiempo (fallando una nota) y guarda una imagen en juego y la de resultados."""
    app, t = crear("ritmo"), 0.0
    ritmo, notas = app.ritmo, app.cancion.notas
    siguiente, doblado_hasta, tecla, en_juego = 0, -1.0, 5, False
    while not ritmo.terminada(t):
        t += DT
        if siguiente < len(notas):
            tecla = app.teclado.indice(notas[siguiente].nota)
            if t >= ritmo.instante(siguiente) - 0.02:
                if siguiente != 3:  # se deja pasar una nota
                    doblado_hasta = t + 3 * DT
                siguiente += 1
        lienzo = cuadro(app, t, tecla, INDICE if t <= doblado_hasta else ABIERTA)
        if not en_juego and ritmo.aciertos == 19 and t <= doblado_hasta - DT:
            guardar("captura_ritmo.png", lienzo)
            en_juego = True
    guardar("captura_resultados.png", cuadro(app, t + DT, tecla, ABIERTA))


if __name__ == "__main__":
    captura_guia()
    captura_ritmo()
