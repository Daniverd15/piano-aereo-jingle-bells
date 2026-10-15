"""Gesto de puño: cerrar la mano un momento para repetir la canción sin tocar el PC.

Solo se atiende en la pantalla de resultados, para que cerrar la mano en
mitad de una canción nunca la reinicie por accidente. El puño no hace sonar
notas: el detector de toques lo descarta (todos los dedos bajan a la vez).
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np

# (punta, articulación media) de índice, medio, anular y meñique.
_DEDOS = ((8, 6), (12, 10), (16, 14), (20, 18))


def es_puno(p: np.ndarray) -> bool:
    """En un puño, la punta de cada dedo queda más cerca de la muñeca que su articulación media."""
    muneca = p[0]
    return all(np.hypot(*(p[punta] - muneca)) < np.hypot(*(p[medio] - muneca)) for punta, medio in _DEDOS)


class GestoPuno:
    SOSTENER = 1.0  # s con el puño cerrado

    def __init__(self) -> None:
        self._inicio: Optional[float] = None
        self._usado = False  # ya disparó: hay que abrir la mano para volver a usarlo
        self.centro: Optional[Tuple[float, float]] = None

    def actualizar(self, manos: Sequence[np.ndarray], t: float) -> Tuple[float, bool]:
        """Devuelve ``(progreso de 0 a 1, si se completó el gesto en este fotograma)``."""
        punos = [p for p in manos if es_puno(p)]
        if not punos:
            self._inicio, self._usado, self.centro = None, False, None
            return 0.0, False
        self.centro = tuple(float(v) for v in punos[0].mean(axis=0))
        if self._usado:
            return 0.0, False
        if self._inicio is None:
            self._inicio = t
        progreso = (t - self._inicio) / self.SOSTENER
        if progreso >= 1.0:
            self._inicio, self._usado = None, True
            return 1.0, True
        return progreso, False
