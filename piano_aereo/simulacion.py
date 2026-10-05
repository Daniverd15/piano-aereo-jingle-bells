"""Mano sintética: permite probar el detector y la interfaz sin cámara."""

from __future__ import annotations

from typing import Sequence

import numpy as np

# Posición horizontal de la base y longitud de índice, medio, anular y meñique,
# en unidades del tamaño de la mano.
_BASES = (-0.45, -0.15, 0.15, 0.45)
_LARGOS = (0.90, 1.00, 0.92, 0.75)


def mano_sintetica(
    cx: float,
    cy: float,
    tam: float = 120.0,
    flexion: Sequence[float] = (0, 0, 0, 0, 0),
    derecha: bool = True,
) -> np.ndarray:
    """Devuelve los 21 puntos ``(x, y)`` de una mano abierta con los dedos hacia arriba.

    ``(cx, cy)`` es la muñeca y ``flexion`` indica cuánto se dobla cada dedo
    (pulgar a meñique), de 0 = estirado a 1 = totalmente doblado.
    """
    p = np.zeros((21, 2))
    for i, (base, largo) in enumerate(zip(_BASES, _LARGOS)):
        largo *= 1.0 - 0.6 * flexion[i + 1]
        nudillo = 5 + 4 * i
        for k, fraccion in enumerate((0.0, 0.45, 0.75, 1.0)):
            p[nudillo + k] = (base * 1.15 ** fraccion, -1.0 - largo * fraccion)
    pulgar = np.array([(-0.35, -0.25), (-0.65, -0.50), (-0.85, -0.75), (-1.00, -0.95)])
    cierre = 0.5 * flexion[0]
    pulgar[2:] += cierre * (p[17] - pulgar[2:]) * np.array([[0.6], [1.0]])
    p[1:5] = pulgar
    if not derecha:
        p[:, 0] *= -1.0
    return p * tam + (cx, cy)
