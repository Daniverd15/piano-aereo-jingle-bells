"""Convierte los puntos de la mano en toques de piano.

Idea central: tocar una tecla es *acortar* un dedo visto desde la cámara,
ya sea doblándolo o inclinándolo hacia delante. Para cada dedo se mide su
longitud aparente (punta-nudillo) dividida por el tamaño de la palma, así la
medida no depende de la distancia a la cámara. Esa longitud se compara con
una referencia de "dedo estirado" que se adapta sola, por lo que no hace
falta calibrar: si el dedo se acorta de golpe más que el umbral, hay toque.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import config

DEDOS = ("pulgar", "índice", "medio", "anular", "meñique")
PUNTAS = (4, 8, 12, 16, 20)
_NUDILLOS = (5, 9, 13, 17)  # base de índice, medio, anular y meñique
LADOS = ("izq", "der")


def escala_palma(p: np.ndarray) -> float:
    """Tamaño de la palma en píxeles (media de sus tres lados)."""
    lados = (p[0] - p[5], p[0] - p[17], p[5] - p[17])
    return max(float(np.mean([np.hypot(v[0], v[1]) for v in lados])), 1e-6)


def extensiones(p: np.ndarray) -> np.ndarray:
    """Longitud aparente de los cinco dedos en unidades de palma."""
    palma = escala_palma(p)
    ext = np.empty(5)
    # El pulgar no se dobla hacia la palma sino que se cierra sobre ella:
    # se mide su distancia a la base del meñique.
    ext[0] = np.hypot(*(p[4] - p[17]))
    for i, nudillo in enumerate(_NUDILLOS, start=1):
        ext[i] = np.hypot(*(p[PUNTAS[i]] - p[nudillo]))
    return ext / palma


@dataclass(frozen=True)
class Toque:
    """Un dedo que pulsa (``pulsa=True``) o suelta una tecla."""

    pulsa: bool
    lado: str
    dedo: int
    x: float = 0.0
    y: float = 0.0
    fuerza: float = 0.0

    @property
    def voz(self) -> Tuple[str, int]:
        return self.lado, self.dedo


@dataclass(frozen=True)
class Lectura:
    """Estado de un dedo para dibujarlo: dónde está y cuánto le falta para tocar."""

    lado: str
    dedo: int
    punta: Tuple[float, float]
    carril_x: float
    progreso: float  # 0 = estirado, 1 = en el umbral de toque
    pulsado: bool


class _EstadoMano:
    def __init__(self, t: float) -> None:
        self.t_inicio = t
        self.t_visto = t
        self.ext: Optional[np.ndarray] = None
        self.reposo = np.zeros(5)
        self.caida = np.zeros(5)
        self.pos = np.zeros((5, 2))  # punta de cada dedo en reposo
        self.pulsado = np.zeros(5, dtype=bool)
        self.t_cambio = np.full(5, -1e9)
        self.centro = np.zeros(2)
        self.muneca = np.zeros(2)
        self.palma = 1.0


class DetectorToques:
    """Detecta toques con histéresis, referencia adaptativa y antirrebote."""

    def __init__(self, sensibilidad: float = config.SENSIBILIDAD, ancho: int = config.ANCHO) -> None:
        self.umbral = sensibilidad
        self.ancho = ancho
        self._manos: Dict[str, _EstadoMano] = {}
        self.lecturas: List[Lectura] = []

    def ajustar(self, delta: float) -> float:
        """Cambia el umbral (más bajo = más sensible) y devuelve el nuevo valor."""
        self.umbral = float(np.clip(self.umbral + delta, config.SENSIBILIDAD_MIN, config.SENSIBILIDAD_MAX))
        return self.umbral

    # ---------------------------------------------------------------- manos
    def _asignar(self, manos: Sequence[np.ndarray]) -> Dict[str, np.ndarray]:
        """Da a cada mano un nombre estable (``izq``/``der``) según su posición.

        No se usa la lateralidad que estima MediaPipe: con la imagen en
        espejo es poco fiable, y aquí solo hace falta no confundir las manos
        entre un fotograma y el siguiente.
        """
        if not manos:
            return {}
        if len(manos) >= 2:
            a, b = sorted(manos[:2], key=lambda p: float(p[:, 0].mean()))
            return {"izq": a, "der": b}
        p = manos[0]
        centro = p.mean(axis=0)
        cercana, distancia = None, float("inf")
        for lado, estado in self._manos.items():
            d = float(np.hypot(*(centro - estado.centro)))
            if d < distancia:
                cercana, distancia = lado, d
        if cercana is not None and distancia < 3.0 * escala_palma(p):
            return {cercana: p}
        lado = "izq" if centro[0] < self.ancho / 2.0 else "der"
        if lado in self._manos:  # ese nombre ya lo tiene otra mano que se perdió
            lado = "der" if lado == "izq" else "izq"
        return {lado: p}

    def actualizar(self, manos: Sequence[np.ndarray], t: float) -> List[Toque]:
        """Procesa las manos de un fotograma (arrays ``(21, 2)`` en píxeles)."""
        eventos: List[Toque] = []
        visibles = self._asignar(manos)
        for lado in list(self._manos):
            estado = self._manos[lado]
            if lado not in visibles and t - estado.t_visto > config.GRACIA:
                eventos.extend(Toque(False, lado, i) for i in np.flatnonzero(estado.pulsado))
                del self._manos[lado]
        self.lecturas = []
        for lado in LADOS:
            if lado in visibles:
                estado = self._manos.get(lado)
                if estado is None:
                    estado = self._manos[lado] = _EstadoMano(t)
                eventos.extend(self._procesar(lado, estado, visibles[lado], t))
        return eventos

    # ---------------------------------------------------------------- dedos
    def _procesar(self, lado: str, m: _EstadoMano, p: np.ndarray, t: float) -> List[Toque]:
        eventos: List[Toque] = []
        puntas = p[list(PUNTAS)]
        ext = extensiones(p)
        palma = escala_palma(p)
        dt = min(max(t - m.t_visto, 1e-3), 0.2)
        if m.ext is None:
            m.ext, m.reposo, m.pos = ext.copy(), ext.copy(), puntas.copy()
            rapidez = 0.0
        else:
            m.ext = m.ext + config.SUAVIZADO * (ext - m.ext)
            rapidez = float(np.hypot(*(p[0] - m.muneca))) / palma / dt
        m.t_visto, m.muneca, m.centro, m.palma = t, p[0].copy(), p.mean(axis=0), palma

        # Referencia de "dedo estirado": sube rápido y baja despacio, de modo
        # que un toque (brusco) destaca pero un cambio de postura se absorbe.
        libres = ~m.pulsado
        lento = 1.0 - math.exp(-dt / config.TAU_REPOSO)
        paso = np.where(m.ext >= m.reposo, 0.5, lento)
        m.reposo = np.where(libres, m.reposo + paso * (m.ext - m.reposo), m.reposo)
        anterior = m.caida
        m.caida = 1.0 - m.ext / np.maximum(m.reposo, 1e-6)

        # La tecla se elige con la posición de la punta *antes* de doblarse:
        # al doblar el dedo (sobre todo el pulgar) la punta se desplaza.
        quietos = m.caida < 0.35 * self.umbral
        m.pos[quietos] += 0.5 * (puntas[quietos] - m.pos[quietos])

        # Rechazo de modo común: un toque es un dedo que baja mientras los
        # demás siguen quietos. A la caída de cada dedo se le resta la mediana
        # de la de los otros dedos largos; si la mano entera se cierra o se
        # relaja, todos bajan a la vez y la caída propia queda cerca de cero.
        propia = m.caida.copy()
        if config.MODO_COMUN:
            for i in range(5):
                otros = [m.caida[j] for j in range(1, 5) if j != i]
                propia[i] -= max(float(np.median(otros)), 0.0)
        candidatos = [i for i in range(5) if libres[i] and propia[i] >= self.umbral]
        if len(candidatos) >= config.CAMBIO_POSTURA:
            # Casi todos los dedos se acortan a la vez: la mano se inclina o
            # se cierra, no es un toque. Se toma como la nueva postura de reposo.
            m.reposo[libres] = m.ext[libres]
            m.caida[libres] = 0.0
            candidatos = []
        listo = t - m.t_inicio >= config.CALENTAMIENTO and rapidez < config.RAPIDEZ_MAX
        dominante = float(m.caida.max())

        for i in range(5):
            if m.pulsado[i]:
                agotado = t - m.t_cambio[i] > config.SOSTENIDO_MAX
                if m.caida[i] < self.umbral * config.SOLTAR or agotado:
                    m.pulsado[i], m.t_cambio[i] = False, t
                    if agotado:
                        m.reposo[i] = m.ext[i]
                    eventos.append(Toque(False, lado, i))
            elif (
                listo
                and i in candidatos
                and m.caida[i] >= config.DOMINANCIA * dominante
                and t - m.t_cambio[i] >= config.REBOTE
            ):
                m.pulsado[i], m.t_cambio[i] = True, t
                velocidad = (m.caida[i] - anterior[i]) / dt  # cuanto más brusco, más fuerte
                fuerza = float(np.clip(0.5 + velocidad / 8.0, 0.5, 1.0))
                eventos.append(Toque(True, lado, i, float(m.pos[i, 0]), float(m.pos[i, 1]), fuerza))

        for i in range(5):
            self.lecturas.append(Lectura(
                lado, i, (float(puntas[i, 0]), float(puntas[i, 1])), float(m.pos[i, 0]),
                float(np.clip(propia[i] / self.umbral, 0.0, 1.0)), bool(m.pulsado[i]),
            ))
        return eventos
