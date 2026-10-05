"""Todo lo que se dibuja: teclado, manos, notas que caen, letra y paneles."""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import config
from .canciones import Cancion, Guia
from .notas import Teclado, color, solfeo
from .texto import escribir, medir
from .toques import Lectura
from .vision import CONEXIONES

Color = Tuple[int, int, int]

BLANCO: Color = (255, 255, 255)
TINTA: Color = (45, 35, 30)
GRIS: Color = (190, 190, 190)
FONDO_PANEL: Color = (28, 20, 16)
DORADO: Color = (63, 210, 255)
ROJO: Color = (70, 70, 240)

MODOS = (("1", "libre", "Libre"), ("2", "guia", "Guía"), ("3", "demo", "Demo"))

AYUDA = (
    ("Cómo tocar", ""),
    ("", "Pon la mano frente a la cámara con los dedos estirados."),
    ("", "Muévela hasta que la punta del dedo quede sobre el carril de la tecla."),
    ("", "Dobla ese dedo, como si pulsaras la tecla, y estíralo para soltarla."),
    ("Teclas", ""),
    ("1  2  3", "Modo libre · Guía (espera a que aciertes) · Demo (suena sola)"),
    ("S", "Cambiar canción: coro o canción completa"),
    ("T", "Cambiar timbre: piano, campanas, caja de música"),
    ("+  -", "Más o menos sensibilidad al doblar el dedo"),
    ("R", "Reiniciar la canción"),
    ("E", "Mostrar u ocultar el esqueleto de la mano"),
    ("F", "Pantalla completa"),
    ("Z X C V B N M , . /", "Tocar las diez teclas con el teclado del PC"),
    ("H", "Mostrar u ocultar esta ayuda"),
    ("Q  Esc", "Salir"),
)


def caja(
    img: np.ndarray, x0: float, y0: float, x1: float, y1: float,
    tono: Color, opacidad: float = 1.0, radio: int = 0,
) -> None:
    """Rectángulo relleno, opcionalmente translúcido y con esquinas redondeadas."""
    x0, y0 = max(int(round(x0)), 0), max(int(round(y0)), 0)
    x1, y1 = min(int(round(x1)), img.shape[1]), min(int(round(y1)), img.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    zona = img[y0:y1, x0:x1]
    capa = zona if opacidad >= 1.0 else zona.copy()
    ancho, alto = x1 - x0, y1 - y0
    radio = max(0, min(radio, ancho // 2, alto // 2))
    if radio == 0:
        capa[:] = tono
    else:
        cv2.rectangle(capa, (radio, 0), (ancho - 1 - radio, alto - 1), tono, -1)
        cv2.rectangle(capa, (0, radio), (ancho - 1, alto - 1 - radio), tono, -1)
        for cx in (radio, ancho - 1 - radio):
            for cy in (radio, alto - 1 - radio):
                cv2.circle(capa, (cx, cy), radio, tono, -1, cv2.LINE_AA)
    if opacidad < 1.0:
        cv2.addWeighted(capa, opacidad, zona, 1.0 - opacidad, 0.0, dst=zona)


def _estrella(img: np.ndarray, cx: float, cy: float, radio: float, tono: Color) -> None:
    puntos = []
    for k in range(10):
        r = radio if k % 2 == 0 else radio * 0.45
        angulo = -math.pi / 2 + k * math.pi / 5
        puntos.append((cx + r * math.cos(angulo), cy + r * math.sin(angulo)))
    cv2.fillPoly(img, [np.array(puntos, dtype=np.int32)], tono, cv2.LINE_AA)


class Interfaz:
    """Dibuja cada capa de la escena sobre un lienzo BGR de ``ANCHO x ALTO``."""

    def __init__(self, teclado: Teclado) -> None:
        self.teclado = teclado
        self._chispas: List[List[float]] = []
        self._colores_chispa: List[Color] = []
        azar = np.random.default_rng(7)
        self._nieve = azar.random((70, 3))  # x, y y tamaño de cada copo, en 0..1
        degradado = np.linspace(0.0, 1.0, config.ALTO)[:, None, None]
        arriba, abajo = np.array((70, 40, 24.0)), np.array((26, 16, 12.0))
        fondo = arriba + (abajo - arriba) * degradado
        self._fondo = np.repeat(fondo, config.ANCHO, axis=1).astype(np.uint8)

    # ------------------------------------------------------------------ fondo
    def fondo(self, imagen: Optional[np.ndarray]) -> np.ndarray:
        """Lienzo nuevo: la cámara oscurecida, o un degradado si no hay imagen."""
        if imagen is None:
            return self._fondo.copy()
        lienzo = cv2.resize(imagen, (config.ANCHO, config.ALTO), interpolation=cv2.INTER_LINEAR)
        return cv2.convertScaleAbs(lienzo, alpha=0.72, beta=0)

    def nieve(self, lienzo: np.ndarray, dt: float) -> None:
        copos = self._nieve
        copos[:, 1] = (copos[:, 1] + dt * (0.04 + 0.06 * copos[:, 2])) % 1.0
        for x, y, tam in copos:
            centro = (int(x * config.ANCHO), int(y * self.teclado.y))
            cv2.circle(lienzo, centro, 1 + int(tam * 2.5), (235, 235, 235), -1, cv2.LINE_AA)

    def carriles(self, lienzo: np.ndarray, objetivo: Optional[int]) -> None:
        t = self.teclado
        if objetivo is not None:
            x0, _, x1, _ = t.rect(objetivo)
            caja(lienzo, x0, config.PISTA_Y_MIN, x1, t.y, color(t.notas[objetivo]), 0.13)
        for i in range(len(t) + 1):
            x = t.rect(min(i, len(t) - 1))[0 if i < len(t) else 2]
            caja(lienzo, x - 1, config.PISTA_Y_MIN, x + 1, t.y, BLANCO, 0.16)

    # ------------------------------------------------------------------ pista
    def pista(self, lienzo: np.ndarray, cancion: Cancion, pulso: float, desde: int) -> None:
        """Notas que caen hacia su tecla; la próxima descansa sobre el teclado."""
        t = self.teclado
        px = config.PX_POR_PULSO
        for nota in cancion.notas[desde:]:
            base = t.y - (nota.inicio - pulso) * px
            cima = base - nota.pulsos * px + 6
            if base <= config.PISTA_Y_MIN:
                break
            base, cima = min(base, t.y - 2), max(cima, config.PISTA_Y_MIN)
            if base - cima < 8:
                continue
            x0, _, x1, _ = t.rect(t.indice(nota.nota))
            caja(lienzo, x0 + 10, cima, x1 - 10, base, color(nota.nota), 0.85, 12)
            if base - cima >= 28:
                escribir(lienzo, nota.silaba.strip("-"), (x0 + x1) / 2, base - 27,
                         18, TINTA, "centro", True)

    # ---------------------------------------------------------------- teclado
    def dibujar_teclado(
        self,
        lienzo: np.ndarray,
        pulsadas: Iterable[int],
        objetivo: Optional[int],
        fallos: Dict[int, float],
        ahora: float,
        con_teclas_pc: bool = False,
    ) -> None:
        t = self.teclado
        pulsadas = set(pulsadas)
        caja(lienzo, 0, t.y - 6, config.ANCHO, config.ALTO, FONDO_PANEL, 0.55)
        for i, nota in enumerate(t.notas):
            x0, y0, x1, y1 = t.rect(i)
            x0, x1 = x0 + 3, x1 - 3
            tono = color(nota)
            tinta = TINTA
            if i in pulsadas:
                caja(lienzo, x0, y0, x1, y1, tono, 0.96, 12)
                tinta = BLANCO
            else:
                caja(lienzo, x0, y0, x1, y1, (246, 246, 246), 0.80, 12)
                caja(lienzo, x0, y0, x1, y0 + 10, tono, 0.95, 5)
                if i == objetivo:
                    latido = 0.5 + 0.25 * math.sin(ahora * 7.0)
                    caja(lienzo, x0, y0, x1, y1, tono, latido, 12)
            edad = ahora - fallos.get(i, -1e9)
            if edad < 0.3:
                caja(lienzo, x0, y0, x1, y1, ROJO, 0.75 * (1.0 - edad / 0.3), 12)
            cx = (x0 + x1) / 2
            escribir(lienzo, solfeo(nota), cx, y1 - 86, 30, tinta, "centro", True)
            escribir(lienzo, nota, cx, y1 - 46, 16, tinta, "centro", opacidad=0.7)
            if con_teclas_pc:
                escribir(lienzo, config.TECLAS_PC[i].upper(), cx, y0 + 18, 15, tinta, "centro",
                         opacidad=0.6)

    # ------------------------------------------------------------------ manos
    def manos(
        self, lienzo: np.ndarray, manos: Sequence[np.ndarray], lecturas: Sequence[Lectura],
        esqueleto: bool = True,
    ) -> None:
        t = self.teclado
        if esqueleto:
            for p in manos:
                puntos = p.astype(np.int32)
                for a, b in CONEXIONES:
                    cv2.line(lienzo, tuple(puntos[a]), tuple(puntos[b]), (240, 240, 240), 2, cv2.LINE_AA)
                for punto in puntos:
                    cv2.circle(lienzo, tuple(punto), 3, (120, 110, 100), -1, cv2.LINE_AA)
        for lectura in lecturas:
            tecla = t.tecla_en(lectura.carril_x)
            tono = color(t.notas[tecla]) if tecla is not None else (150, 150, 150)
            x, y = int(lectura.punta[0]), int(lectura.punta[1])
            if tecla is not None and y < t.y:
                # Plomada: muestra sobre qué tecla caerá el dedo.
                cv2.line(lienzo, (x, y), (x, t.y), tono, 1, cv2.LINE_AA)
                cv2.circle(lienzo, (x, t.y), 4, tono, -1, cv2.LINE_AA)
            if lectura.pulsado:
                cv2.circle(lienzo, (x, y), 17, BLANCO, 3, cv2.LINE_AA)
                cv2.circle(lienzo, (x, y), 12, tono, -1, cv2.LINE_AA)
            else:
                cv2.circle(lienzo, (x, y), 9, tono, -1, cv2.LINE_AA)
                cv2.circle(lienzo, (x, y), 9, BLANCO, 2, cv2.LINE_AA)
                if lectura.progreso > 0.15:
                    # Arco que se cierra a medida que el dedo se acerca al toque.
                    cv2.ellipse(lienzo, (x, y), (15, 15), -90, 0, 360 * lectura.progreso,
                                BLANCO, 3, cv2.LINE_AA)

    # ---------------------------------------------------------------- chispas
    def chispear(self, tecla: int) -> None:
        t = self.teclado
        azar = np.random.default_rng()
        for _ in range(12):
            angulo = azar.uniform(-math.pi * 0.85, -math.pi * 0.15)
            rapidez = azar.uniform(160, 420)
            self._chispas.append([t.centro(tecla) + azar.uniform(-30, 30), t.y,
                                  rapidez * math.cos(angulo), rapidez * math.sin(angulo), 0.5])
            self._colores_chispa.append(color(t.notas[tecla]))

    def chispas(self, lienzo: np.ndarray, dt: float) -> None:
        vivas, colores = [], []
        for chispa, tono in zip(self._chispas, self._colores_chispa):
            chispa[0] += chispa[2] * dt
            chispa[1] += chispa[3] * dt
            chispa[3] += 900 * dt
            chispa[4] -= dt
            if chispa[4] > 0:
                radio = 1 + int(6 * chispa[4])
                cv2.circle(lienzo, (int(chispa[0]), int(chispa[1])), radio, tono, -1, cv2.LINE_AA)
                vivas.append(chispa)
                colores.append(tono)
        self._chispas, self._colores_chispa = vivas, colores

    # -------------------------------------------------------------------- HUD
    def barra(self, lienzo: np.ndarray, modo: str, detalle: str, progreso: Optional[float]) -> None:
        caja(lienzo, 0, 0, config.ANCHO, 60, FONDO_PANEL, 0.78)
        escribir(lienzo, "Piano Aéreo", 20, 13, 25, BLANCO, negrita=True)
        x = 190
        for tecla, identificador, nombre in MODOS:
            etiqueta = "%s  %s" % (tecla, nombre)
            ancho = medir(etiqueta, 17, True)[0] + 28
            activo = identificador == modo
            caja(lienzo, x, 13, x + ancho, 47, DORADO if activo else (80, 68, 60), 1.0, 16)
            escribir(lienzo, etiqueta, x + 14, 18, 17, TINTA if activo else BLANCO, negrita=True)
            x += ancho + 10
        escribir(lienzo, detalle, config.ANCHO - 20, 9, 16, BLANCO, "der")
        escribir(lienzo, "H ayuda  ·  S canción  ·  T timbre  ·  Q salir", config.ANCHO - 20, 33,
                 13, GRIS, "der")
        if progreso is not None:
            caja(lienzo, 0, 60, config.ANCHO, 65, (60, 50, 45), 0.8)
            caja(lienzo, 0, 60, config.ANCHO * min(max(progreso, 0.0), 1.0), 65, DORADO)

    def letra(self, lienzo: np.ndarray, cancion: Cancion, actual: int) -> None:
        """Línea de karaoke: la frase en curso con la sílaba actual resaltada."""
        if actual >= len(cancion):
            return
        primero, fin = cancion.frase_de(actual)
        tam, espacio = 28, 10
        trozos = []
        total = 0
        for i in range(primero, fin):
            silaba = cancion.notas[i].silaba
            ancho = medir(silaba, tam, True)[0]
            trozos.append((i, silaba, ancho))
            total += ancho + (0 if silaba.endswith("-") else espacio)
        x = (config.ANCHO - total) / 2
        caja(lienzo, x - 22, 72, x + total + 22, 114, FONDO_PANEL, 0.72, 20)
        for i, silaba, ancho in trozos:
            tono = DORADO if i < actual else BLANCO if i == actual else (165, 165, 165)
            escribir(lienzo, silaba, x, 74, tam, tono, negrita=True)
            if i == actual:
                caja(lienzo, x, 108, x + ancho, 111, BLANCO, 1.0, 1)
            x += ancho + (0 if silaba.endswith("-") else espacio)

    def marcador(self, lienzo: np.ndarray, guia: Guia) -> None:
        cadena = "Aciertos %d/%d   ·   Errores %d   ·   Racha %d" % (
            guia.aciertos, len(guia.cancion), guia.errores, guia.racha)
        ancho = medir(cadena, 16)[0]
        caja(lienzo, 14, 76, 14 + ancho + 28, 110, FONDO_PANEL, 0.72, 17)
        escribir(lienzo, cadena, 28, 82, 16, BLANCO)

    def aviso(self, lienzo: np.ndarray, cadena: str, y: int = 74, tam: int = 22) -> None:
        ancho, alto = medir(cadena, tam, True)
        x = (config.ANCHO - ancho) / 2
        caja(lienzo, x - 24, y - 4, x + ancho + 24, y + alto + 6, FONDO_PANEL, 0.78, 20)
        escribir(lienzo, cadena, x, y, tam, BLANCO, negrita=True)

    def panel_final(self, lienzo: np.ndarray, guia: Guia, ahora: float) -> None:
        cx, cy = config.ANCHO // 2, 300
        caja(lienzo, cx - 290, cy - 150, cx + 290, cy + 150, FONDO_PANEL, 0.92, 26)
        escribir(lienzo, "¡Canción completada!", cx, cy - 128, 36, BLANCO, "centro", True)
        for k in range(3):
            tono = DORADO if k < guia.estrellas else (95, 85, 80)
            _estrella(lienzo, cx + (k - 1) * 84, cy - 28, 34, tono)
        resumen = "Precisión %d %%   ·   Tiempo %d s   ·   Mejor racha %d" % (
            round(guia.precision * 100), round(guia.duracion(ahora)), guia.mejor_racha)
        escribir(lienzo, resumen, cx, cy + 36, 21, BLANCO, "centro")
        escribir(lienzo, "R  repetir     ·     S  otra canción     ·     1  modo libre",
                 cx, cy + 92, 17, GRIS, "centro")

    def ayuda(self, lienzo: np.ndarray) -> None:
        x0, y0, x1 = 250, 84, config.ANCHO - 250
        caja(lienzo, x0, y0, x1, y0 + 34 + 30 * len(AYUDA), FONDO_PANEL, 0.93, 24)
        y = y0 + 18
        for tecla, descripcion in AYUDA:
            if not descripcion:
                escribir(lienzo, tecla, x0 + 30, y, 20, DORADO, negrita=True)
            elif not tecla:
                escribir(lienzo, descripcion, x0 + 30, y + 2, 17, BLANCO)
            else:
                escribir(lienzo, tecla, x0 + 30, y + 2, 17, BLANCO, negrita=True)
                escribir(lienzo, descripcion, x0 + 220, y + 2, 17, (215, 215, 215))
            y += 30
