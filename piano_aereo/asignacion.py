"""Posición de cinco dedos: cada dedo de la mano recibe una tecla automáticamente.

Como en la técnica del piano, la mano se coloca sobre cinco teclas seguidas y
cada dedo toca la suya, sin apuntar. La tecla central es la que queda bajo el
centro de la mano; al moverla, las cinco teclas se desplazan con ella.

Los dedos se ordenan por su posición en pantalla (el de más a la izquierda
toca la nota más grave), así que no hace falta saber si la mano es la derecha
o la izquierda ni si la palma o el dorso miran a la cámara.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from .notas import Teclado
from .toques import Lectura

# Numeración de los dedos en el piano: 1 = pulgar ... 5 = meñique.
NUMERO_DEDO = (1, 2, 3, 4, 5)
HISTERESIS = 0.3  # teclas de margen antes de desplazar la posición


class CincoDedos:
    """Mantiene, para cada mano, qué tecla toca cada dedo."""

    def __init__(self, teclado: Teclado) -> None:
        self.teclado = teclado
        self._base: Dict[str, int] = {}  # mano -> primera de sus cinco teclas
        self._teclas: Dict[str, Dict[int, int]] = {}  # mano -> {dedo: tecla}

    def reiniciar(self) -> None:
        self._base.clear()
        self._teclas.clear()

    def _posicion(self, x: float) -> float:
        """Posición horizontal en teclas: 0.0 es el centro de la primera tecla."""
        return (x - self.teclado.x) / self.teclado.ancho_tecla - 0.5

    def _elegir_base(self, lado: str, centro: float) -> int:
        """Primera tecla de la posición, con histéresis para que no parpadee en el borde."""
        ultima = len(self.teclado) - 5
        deseada = self._posicion(centro) - 2.0  # la tecla central queda bajo el centro de la mano
        anterior = self._base.get(lado)
        if anterior is not None:
            if abs(deseada - anterior) < 0.5 + HISTERESIS:
                return anterior
            if anterior == 0 and deseada < 0.5 + HISTERESIS:
                return anterior
            if anterior == ultima and deseada > ultima - 0.5 - HISTERESIS:
                return anterior
        return int(np.clip(round(deseada), 0, ultima))

    def actualizar(self, lecturas: Iterable[Lectura]) -> None:
        """Recalcula las teclas de cada mano visible a partir de sus dedos en reposo."""
        por_mano: Dict[str, List[Lectura]] = {}
        for lectura in lecturas:
            por_mano.setdefault(lectura.lado, []).append(lectura)
        for lado in list(self._base):
            if lado not in por_mano:
                del self._base[lado]
                self._teclas.pop(lado, None)
        for lado, dedos in por_mano.items():
            if len(dedos) < 5 or (lado in self._teclas and any(d.pulsado for d in dedos)):
                continue  # con un dedo pulsado la posición no se mueve
            orden = sorted(dedos, key=lambda d: d.carril_x)
            base = self._elegir_base(lado, float(np.median([d.carril_x for d in dedos])))
            self._base[lado] = base
            self._teclas[lado] = {d.dedo: base + k for k, d in enumerate(orden)}

    def tecla(self, lado: str, dedo: int) -> Optional[int]:
        return self._teclas.get(lado, {}).get(dedo)

    def teclas(self) -> Dict[Tuple[str, int], int]:
        """Todas las asignaciones: ``(mano, dedo) -> tecla``."""
        return {(lado, dedo): tecla for lado, teclas in self._teclas.items() for dedo, tecla in teclas.items()}

    def dedo_para(self, tecla: int) -> Optional[Tuple[str, int]]:
        """Qué ``(mano, dedo)`` toca esa tecla, si alguna mano la cubre."""
        for (lado, dedo), asignada in self.teclas().items():
            if asignada == tecla:
                return lado, dedo
        return None
