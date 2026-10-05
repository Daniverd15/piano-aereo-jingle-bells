"""Genera ``docs/captura.png``: la interfaz en modo Guía con manos simuladas.

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


def main() -> None:
    app = App(crear_argumentos().parse_args(["--sin-camara", "--sin-sonido", "--modo", "guia"]))
    x_indice = mano_sintetica(0, 0, tam=105)[8][0]
    izquierda = mano_sintetica(215, 470, tam=105, derecha=False)
    t = 0.0

    def cuadro(cx, flexion):
        nonlocal t
        t += DT
        app.procesar_manos([izquierda, mano_sintetica(cx, 470, tam=105, flexion=flexion)], t)
        app.avanzar(t, DT)
        return app.componer(t)

    # Toca las ocho primeras notas y deja el dedo pulsando la novena.
    for n, nota in enumerate(app.cancion.notas[:9]):
        cx = app.teclado.centro(app.teclado.indice(nota.nota)) - x_indice
        for _ in range(12):
            cuadro(cx, (0, 0, 0, 0, 0))
        for _ in range(4):
            lienzo = cuadro(cx, (0, 1, 0, 0, 0))
        if n < 8:
            for _ in range(6):
                cuadro(cx, (0, 0, 0, 0, 0))
    destino = RAIZ / "docs" / "captura.png"
    destino.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(destino), lienzo)
    print("Guardada", destino)


if __name__ == "__main__":
    main()
