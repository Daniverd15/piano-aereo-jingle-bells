"""Decoración navideña: un árbol que se adorna con cada acierto y fuegos artificiales.

El árbol ocupa el carril de Si4, la única tecla que Jingle Bells no usa, así
que nunca tapa las notas que caen.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import cv2
import numpy as np

from .notas import color

Color = Tuple[int, int, int]

VERDE = (60, 125, 35)
VERDE_OSCURO = (35, 85, 20)
TRONCO = (35, 70, 115)
ORO = (63, 210, 255)
APAGADO = (110, 110, 110)
_TONOS = tuple(color(n) for n in ("C", "D", "E", "F", "G", "A", "B"))


class Arbol:
    """Árbol de tres pisos con ``ADORNOS`` bolas que se encienden según el progreso."""

    ADORNOS = 30

    def __init__(self, cx: int, cima: int, alto: int) -> None:
        self.cx, self.cima, self.alto = cx, cima, alto
        ancho = int(alto * 0.42)
        self._pisos: List[np.ndarray] = []
        for k in range(3):  # tres triángulos solapados, más anchos hacia abajo
            y0 = cima + int(alto * (0.04 + 0.27 * k))
            y1 = cima + int(alto * (0.42 + 0.25 * k))
            mitad = int(ancho * (0.55 + 0.25 * k) / 2)
            self._pisos.append(np.array([(cx, y0), (cx - mitad, y1), (cx + mitad, y1)], np.int32))
        self._tronco = (cx - 11, cima + int(alto * 0.92), cx + 11, cima + alto)
        # Posiciones fijas de las bolas, repartidas dentro de la silueta (de arriba abajo).
        azar = np.random.default_rng(12)
        puntos = []
        while len(puntos) < self.ADORNOS:
            y = cima + alto * azar.uniform(0.18, 0.88)
            x = cx + azar.uniform(-1, 1) * ancho / 2
            if any(cv2.pointPolygonTest(p, (float(x), float(y)), True) > 7 for p in self._pisos):
                puntos.append((int(x), int(y)))
        self._bolas = sorted(puntos, key=lambda p: -p[1])  # se encienden de abajo arriba

    def dibujar(self, lienzo: np.ndarray, progreso: float, ahora: float, pulso: float,
                completo: bool) -> None:
        x0, x1 = self.cx - int(self.alto * 0.3), self.cx + int(self.alto * 0.3)
        y0, y1 = max(self.cima - 30, 0), min(self.cima + self.alto + 2, lienzo.shape[0])
        zona = lienzo[y0:y1, x0:x1]
        capa = zona.copy()
        desplazar = np.array([x0, y0], np.int32)
        tx0, ty0, tx1, ty1 = self._tronco
        cv2.rectangle(capa, (tx0 - x0, ty0 - y0), (tx1 - x0, ty1 - y0), TRONCO, -1)
        for piso in self._pisos:
            cv2.fillPoly(capa, [piso - desplazar], VERDE, cv2.LINE_AA)
            cv2.polylines(capa, [piso - desplazar], True, VERDE_OSCURO, 2, cv2.LINE_AA)
        cv2.addWeighted(capa, 0.88, zona, 0.12, 0, dst=zona)

        encendidas = int(round(min(max(progreso, 0.0), 1.0) * self.ADORNOS))
        for k, (x, y) in enumerate(self._bolas):
            if k < encendidas:
                # Las luces parpadean a tempo: la mitad se apaga un poco en cada pulso.
                brillo = 1.0 if (int(pulso * 2) + k) % 2 == 0 else 0.75
                tono = tuple(int(c * brillo) for c in _TONOS[k % len(_TONOS)])
                cv2.circle(lienzo, (x, y), 6, tono, -1, cv2.LINE_AA)
                cv2.circle(lienzo, (x - 2, y - 2), 2, (255, 255, 255), -1, cv2.LINE_AA)
            else:
                cv2.circle(lienzo, (x, y), 3, VERDE_OSCURO, -1, cv2.LINE_AA)

        cima = (self.cx, self.cima)
        if completo:
            for k in range(8):  # destellos de la estrella
                angulo = ahora * 1.5 + k * math.pi / 4
                largo = 26 + 6 * math.sin(ahora * 6 + k)
                fin = (int(cima[0] + largo * math.cos(angulo)), int(cima[1] + largo * math.sin(angulo)))
                cv2.line(lienzo, cima, fin, ORO, 2, cv2.LINE_AA)
        estrella(lienzo, cima[0], cima[1], 17, ORO if completo else APAGADO, relleno=completo)


def estrella(img: np.ndarray, cx: float, cy: float, radio: float, tono: Color, relleno: bool = True) -> None:
    puntos = []
    for k in range(10):
        r = radio if k % 2 == 0 else radio * 0.45
        angulo = -math.pi / 2 + k * math.pi / 5
        puntos.append((cx + r * math.cos(angulo), cy + r * math.sin(angulo)))
    poligono = [np.array(puntos, dtype=np.int32)]
    if relleno:
        cv2.fillPoly(img, poligono, tono, cv2.LINE_AA)
    else:
        cv2.polylines(img, poligono, True, tono, 2, cv2.LINE_AA)


class Fuegos:
    """Fuegos artificiales: cohetes programados que estallan en chispas con gravedad."""

    def __init__(self) -> None:
        self._azar = np.random.default_rng()
        self._pendientes: List[Tuple[float, float, float, Color]] = []  # (cuándo, x, y, color)
        self._chispas = np.zeros((0, 6))  # x, y, vx, vy, vida, índice de color
        self._colores: List[Color] = []

    @property
    def activos(self) -> bool:
        return bool(self._pendientes) or len(self._chispas) > 0

    def celebrar(self, ahora: float, ancho: int, alto: int, estallidos: int = 7) -> None:
        for k in range(estallidos):
            cuando = ahora + 0.35 * k + self._azar.uniform(0, 0.2)
            # A los lados, para no tapar el panel de resultados del centro.
            lado = (0.03, 0.22) if k % 2 == 0 else (0.72, 0.86)
            x = self._azar.uniform(*lado) * ancho
            y = self._azar.uniform(0.16, 0.45) * alto
            self._pendientes.append((cuando, x, y, _TONOS[k % len(_TONOS)]))

    def limpiar(self) -> None:
        self._pendientes, self._chispas, self._colores = [], np.zeros((0, 6)), []

    def dibujar(self, lienzo: np.ndarray, ahora: float, dt: float) -> None:
        nuevos = [p for p in self._pendientes if p[0] <= ahora]
        self._pendientes = [p for p in self._pendientes if p[0] > ahora]
        for _, x, y, tono in nuevos:
            n = 48
            angulos = self._azar.uniform(0, 2 * math.pi, n)
            rapidez = self._azar.uniform(90, 260, n)
            self._colores.append(tono)
            bloque = np.column_stack([
                np.full(n, x), np.full(n, y), rapidez * np.cos(angulos), rapidez * np.sin(angulos),
                self._azar.uniform(0.9, 1.4, n), np.full(n, len(self._colores) - 1),
            ])
            self._chispas = np.vstack([self._chispas, bloque])
        if not len(self._chispas):
            return
        c = self._chispas
        c[:, 0] += c[:, 2] * dt
        c[:, 1] += c[:, 3] * dt
        c[:, 3] += 160 * dt  # gravedad
        c[:, 2:4] *= 1.0 - 0.9 * dt  # rozamiento del aire
        c[:, 4] -= dt
        self._chispas = c[c[:, 4] > 0]
        for x, y, _, _, vida, k in self._chispas:
            tono = self._colores[int(k)]
            radio = 1 + int(2.5 * min(vida, 1.0))
            cv2.circle(lienzo, (int(x), int(y)), radio, tono, -1, cv2.LINE_AA)
