"""Todo lo que se dibuja: teclado, manos, notas que caen, letra y paneles."""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import config
from .canciones import Cancion, Guia, Ritmo
from .notas import Teclado, color, solfeo
from .texto import escribir, medir
from .toques import Lectura
from .vision import CONEXIONES

Color = Tuple[int, int, int]

BLANCO: Color = (255, 255, 255)
TINTA: Color = (45, 35, 30)
GRIS: Color = (190, 190, 190)
APAGADO: Color = (95, 85, 80)
FONDO_PANEL: Color = (28, 20, 16)
DORADO: Color = (63, 210, 255)
VERDE: Color = (120, 225, 90)
ROJO: Color = (70, 70, 240)

MODOS = (("1", "libre", "Libre"), ("2", "guia", "Guía"), ("3", "ritmo", "Ritmo"), ("4", "demo", "Demo"))
# Del nivel más bajo al más alto: azul, verde, amarillo, naranja.
_TONO_ESPECTRO = ((180, 120, 60), (120, 200, 90), (63, 210, 255), (40, 140, 255))
COLOR_MANO = {"izq": (70, 135, 40), "der": (175, 95, 35)}  # fondo del número de dedo: verde y azul
CARTELES = {"perfecto": ("¡Perfecto!", DORADO), "bien": ("Bien", VERDE), "fallo": ("Fallo", ROJO)}
COLOR_NOTA = {"S": DORADO, "A": VERDE, "B": (241, 196, 46), "C": (28, 159, 255), "D": ROJO}

AYUDA = (
    ("Cómo tocar", ""),
    ("", "Pon la mano frente a la cámara con los dedos estirados."),
    ("", "Muévela hasta que la punta del dedo quede sobre el carril de la tecla."),
    ("", "Dobla ese dedo, como si pulsaras la tecla, y estíralo para soltarla."),
    ("Modos", ""),
    ("1", "Libre: piano sin más"),
    ("2", "Guía: la canción espera a que toques la nota correcta"),
    ("3", "Ritmo: toca cada nota justo cuando llega al teclado y suma puntos"),
    ("4", "Demo: la canción suena sola"),
    ("Teclas", ""),
    ("S   D", "Cambiar canción (coro / completa)  ·  Cambiar dificultad (velocidad)"),
    ("T   P", "Cambiar timbre  ·  Pista de acompañamiento sí / no"),
    ("+   -", "Más o menos sensibilidad al doblar el dedo"),
    ("5", "Forma de tocar: apuntar con el dedo  /  cinco dedos (cada dedo, una tecla)"),
    ("A", "Asistencia: perdona los toques que caen al borde de la tecla"),
    ("R   F   E", "Reiniciar  ·  Pantalla completa  ·  Esqueleto de la mano"),
    ("G   I", "Grabar vídeo y audio  ·  Guardar captura de pantalla"),
    ("O   L", "Espectro de frecuencias  ·  Corregir el retraso (tras el modo Ritmo)"),
    ("Puño", "En la pantalla de resultados, cierra la mano 1 s para repetir"),
    ("Z X C V B N M , . /", "Tocar las diez teclas con el teclado del PC"),
    ("H   Q", "Esta ayuda  ·  Salir"),
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


def _miles(n: int) -> str:
    return "{:,}".format(n).replace(",", " ")


class Interfaz:
    """Dibuja cada capa de la escena sobre un lienzo BGR de ``ANCHO x ALTO``."""

    def __init__(self, teclado: Teclado) -> None:
        self.teclado = teclado
        self._chispas: List[List[float]] = []
        self._colores_chispa: List[Color] = []
        self._carteles: List[Tuple[str, Color, int, float]] = []
        self._azar = np.random.default_rng(7)
        self._nieve = self._azar.random((70, 3))  # x, y y tamaño de cada copo, en 0..1
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

    def nieve(self, lienzo: np.ndarray, dt: float, puntas: Sequence[Tuple[float, float]] = ()) -> None:
        """Copos que caen; los que pasan cerca de la punta de un dedo se apartan."""
        copos = self._nieve
        copos[:, 1] = (copos[:, 1] + dt * (0.04 + 0.06 * copos[:, 2])) % 1.0
        if len(puntas):
            px = copos[:, 0] * config.ANCHO
            py = copos[:, 1] * self.teclado.y
            for x, y in puntas:
                dx, dy = px - x, py - y
                distancia = np.hypot(dx, dy)
                cerca = distancia < 60
                empuje = (60 - distancia[cerca]) * 6.0 * dt / config.ANCHO
                copos[cerca, 0] += np.sign(dx[cerca] + 1e-6) * empuje
            copos[:, 0] %= 1.0
        for x, y, tam in copos:
            centro = (int(x * config.ANCHO), int(y * self.teclado.y))
            cv2.circle(lienzo, centro, 1 + int(tam * 2.5), (235, 235, 235), -1, cv2.LINE_AA)

    def carriles(self, lienzo: np.ndarray, objetivo: Optional[int], autopista: bool = False) -> None:
        t = self.teclado
        if autopista:
            # Oscurece la zona de juego para que las notas destaquen sobre la cámara.
            caja(lienzo, t.x, config.PISTA_Y_MIN, t.x + t.ancho, t.y, (12, 8, 6), 0.32)
        if objetivo is not None:
            x0, _, x1, _ = t.rect(objetivo)
            caja(lienzo, x0, config.PISTA_Y_MIN, x1, t.y, color(t.notas[objetivo]), 0.13)
        for i in range(len(t) + 1):
            x = t.rect(min(i, len(t) - 1))[0 if i < len(t) else 2]
            caja(lienzo, x - 1, config.PISTA_Y_MIN, x + 1, t.y, BLANCO, 0.16)
        if autopista:
            # Línea de golpe: ahí hay que tocar la nota.
            caja(lienzo, t.x, t.y - 9, t.x + t.ancho, t.y - 4, BLANCO, 0.85, 2)

    # ------------------------------------------------------------------ pista
    def pista(
        self, lienzo: np.ndarray, cancion: Cancion, pulso: float, desde: int,
        estados: Optional[Sequence[Optional[str]]] = None,
    ) -> None:
        """Notas que caen hacia su tecla y llegan a la línea de golpe en su pulso.

        ``estados`` (modo Ritmo) oculta las notas acertadas y apaga las falladas.
        """
        t = self.teclado
        px = config.PX_POR_PULSO
        for i in range(desde, len(cancion.notas)):
            nota = cancion.notas[i]
            base = t.y - 6 - (nota.inicio - pulso) * px
            cima = base - nota.pulsos * px + 6
            if base <= config.PISTA_Y_MIN:
                break
            estado = estados[i] if estados is not None else None
            if estado in ("perfecto", "bien"):
                continue
            base, cima = min(base, t.y - 2), max(cima, config.PISTA_Y_MIN)
            if base - cima < 8:
                continue
            x0, _, x1, _ = t.rect(t.indice(nota.nota))
            if estado == "fallo":
                caja(lienzo, x0 + 10, cima, x1 - 10, base, APAGADO, 0.55, 12)
                continue
            # Gema: borde claro, cuerpo del color de la nota y brillo arriba.
            caja(lienzo, x0 + 8, cima, x1 - 8, base, BLANCO, 0.9, 13)
            caja(lienzo, x0 + 11, cima + 3, x1 - 11, base - 3, color(nota.nota), 1.0, 10)
            if base - cima >= 20:
                caja(lienzo, x0 + 16, cima + 6, x1 - 16, cima + 11, BLANCO, 0.45, 3)
            if base - cima >= 30:
                escribir(lienzo, nota.silaba.strip("-"), (x0 + x1) / 2, base - 29,
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
        asignadas: Optional[Dict[Tuple[str, int], int]] = None,
    ) -> None:
        t = self.teclado
        pulsadas = set(pulsadas)
        digitacion: Dict[int, List[Tuple[str, int]]] = {}
        for (lado, dedo), tecla in sorted((asignadas or {}).items()):
            digitacion.setdefault(tecla, []).append((lado, dedo))
        caja(lienzo, 0, t.y - 3, config.ANCHO, config.ALTO, FONDO_PANEL, 0.55)
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
            # Cinco dedos: el número de dedo que toca cada tecla (1 pulgar ... 5 meñique).
            dedos = digitacion.get(i, [])
            for k, (lado, dedo) in enumerate(dedos):
                bx = int(cx + (k - (len(dedos) - 1) / 2.0) * 30)
                cv2.circle(lienzo, (bx, y0 + 36), 13, COLOR_MANO[lado], -1, cv2.LINE_AA)
                escribir(lienzo, str(dedo + 1), bx, y0 + 25, 17, BLANCO, "centro", True)

    # ------------------------------------------------------------------ manos
    def manos(
        self, lienzo: np.ndarray, manos: Sequence[np.ndarray], lecturas: Sequence[Lectura],
        esqueleto: bool = True,
        asignadas: Optional[Dict[Tuple[str, int], int]] = None,
        resaltar: Optional[Tuple[str, int]] = None,
        ahora: float = 0.0,
    ) -> None:
        """Esqueleto y puntas de los dedos.

        Con ``asignadas`` (cinco dedos) cada punta se une a su tecla; si no, la
        línea cae en vertical sobre el carril. ``resaltar`` marca el dedo que
        debe tocar la siguiente nota.
        """
        t = self.teclado
        if esqueleto:
            for p in manos:
                puntos = p.astype(np.int32)
                for a, b in CONEXIONES:
                    cv2.line(lienzo, tuple(puntos[a]), tuple(puntos[b]), (240, 240, 240), 2, cv2.LINE_AA)
                for punto in puntos:
                    cv2.circle(lienzo, tuple(punto), 3, (120, 110, 100), -1, cv2.LINE_AA)
        for lectura in lecturas:
            if asignadas is not None:
                tecla = asignadas.get((lectura.lado, lectura.dedo))
            else:
                tecla = t.tecla_en(lectura.carril_x)
            tono = color(t.notas[tecla]) if tecla is not None else (150, 150, 150)
            x, y = int(lectura.punta[0]), int(lectura.punta[1])
            if tecla is not None and y < t.y:
                # Plomada: muestra qué tecla tocará el dedo.
                destino = (t.centro(tecla), t.y) if asignadas is not None else (x, t.y)
                cv2.line(lienzo, (x, y), destino, tono, 1, cv2.LINE_AA)
                cv2.circle(lienzo, destino, 4, tono, -1, cv2.LINE_AA)
            if resaltar == (lectura.lado, lectura.dedo) and not lectura.pulsado:
                radio = int(24 + 4 * math.sin(ahora * 8.0))
                cv2.circle(lienzo, (x, y), radio, DORADO, 3, cv2.LINE_AA)
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

    # ------------------------------------------------------- chispas y carteles
    def chispear(self, tecla: int, cantidad: int = 12) -> None:
        t = self.teclado
        for _ in range(cantidad):
            angulo = self._azar.uniform(-math.pi * 0.85, -math.pi * 0.15)
            rapidez = self._azar.uniform(160, 420) * (1.0 + cantidad / 40.0)
            self._chispas.append([t.centro(tecla) + self._azar.uniform(-30, 30), t.y,
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

    def cartel(self, tecla: int, grado: str, ahora: float) -> None:
        """Anuncia sobre una tecla cómo se tocó la nota (Perfecto, Bien, Fallo)."""
        cadena, tono = CARTELES[grado]
        x = self.teclado.centro(tecla)
        # Un cartel nuevo sustituye al que hubiera en la misma tecla, para no encimarlos.
        self._carteles = [c for c in self._carteles if c[2] != x]
        self._carteles.append((cadena, tono, x, ahora))

    def carteles(self, lienzo: np.ndarray, ahora: float) -> None:
        duracion = 0.7
        self._carteles = [c for c in self._carteles if ahora - c[3] < duracion]
        for cadena, tono, x, t0 in self._carteles:
            avance = (ahora - t0) / duracion
            ancho, alto = medir(cadena, 24, True)
            y = self.teclado.y - 58 - 50 * avance
            opacidad = min(1.0, 2.0 * (1.0 - avance))
            caja(lienzo, x - ancho / 2 - 12, y - 3, x + ancho / 2 + 12, y + alto + 4,
                 FONDO_PANEL, 0.8 * opacidad, 16)
            escribir(lienzo, cadena, x, y, 24, tono, "centro", True, opacidad)

    def limpiar_efectos(self) -> None:
        self._chispas, self._colores_chispa, self._carteles = [], [], []

    # -------------------------------------------------------------------- HUD
    def barra(self, lienzo: np.ndarray, modo: str, detalle: str, progreso: Optional[float]) -> None:
        caja(lienzo, 0, 0, config.ANCHO, 60, FONDO_PANEL, 0.78)
        escribir(lienzo, "Piano Aéreo", 20, 13, 25, BLANCO, negrita=True)
        x = 184
        for tecla, identificador, nombre in MODOS:
            etiqueta = "%s  %s" % (tecla, nombre)
            ancho = medir(etiqueta, 17, True)[0] + 26
            activo = identificador == modo
            caja(lienzo, x, 13, x + ancho, 47, DORADO if activo else (80, 68, 60), 1.0, 16)
            escribir(lienzo, etiqueta, x + 13, 18, 17, TINTA if activo else BLANCO, negrita=True)
            x += ancho + 8
        escribir(lienzo, detalle, config.ANCHO - 20, 9, 16, BLANCO, "der")
        escribir(lienzo, "H ayuda  ·  S canción  ·  D dificultad  ·  T timbre  ·  Q salir",
                 config.ANCHO - 20, 33, 13, GRIS, "der")
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

    def _pastilla(self, lienzo: np.ndarray, cadena: str) -> None:
        ancho = medir(cadena, 16)[0]
        caja(lienzo, 14, 76, 14 + ancho + 28, 110, FONDO_PANEL, 0.72, 17)
        escribir(lienzo, cadena, 28, 82, 16, BLANCO)

    def marcador(self, lienzo: np.ndarray, guia: Guia) -> None:
        self._pastilla(lienzo, "Aciertos %d/%d   ·   Errores %d   ·   Racha %d" % (
            guia.aciertos, len(guia.cancion), guia.errores, guia.racha))

    def marcador_ritmo(self, lienzo: np.ndarray, ritmo: Ritmo) -> None:
        self._pastilla(lienzo, "Puntos %s   ·   Aciertos %d/%d" % (
            _miles(ritmo.puntos), ritmo.aciertos, len(ritmo.cancion)))
        # Combo y multiplicador, grandes, a la derecha.
        x = config.ANCHO - 96
        caja(lienzo, x - 78, 76, x + 78, 196, FONDO_PANEL, 0.72, 22)
        escribir(lienzo, str(ritmo.combo), x, 76, 52, BLANCO if ritmo.combo else GRIS, "centro", True)
        escribir(lienzo, "COMBO", x, 138, 14, GRIS, "centro", True)
        nivel = ritmo.multiplicador
        tono = (GRIS, VERDE, (241, 196, 46), DORADO)[nivel - 1]
        escribir(lienzo, "x%d" % nivel, x, 158, 26, tono, "centro", True)
        if nivel < 4:  # barra de avance hacia el siguiente multiplicador
            avance = (ritmo.combo % ritmo.COMBO_POR_NIVEL) / float(ritmo.COMBO_POR_NIVEL)
            caja(lienzo, x - 56, 190, x + 56, 193, APAGADO, 1.0, 1)
            caja(lienzo, x - 56, 190, x - 56 + 112 * avance, 193, tono, 1.0, 1)

    def aviso(self, lienzo: np.ndarray, cadena: str, y: int = 74, tam: int = 22) -> None:
        ancho, alto = medir(cadena, tam, True)
        x = (config.ANCHO - ancho) / 2
        margen = max(24, tam // 2)
        caja(lienzo, x - margen, y - 4, x + ancho + margen, y + alto + 6, FONDO_PANEL, 0.78,
             min(40, (alto + 10) // 2))
        escribir(lienzo, cadena, x, y, tam, BLANCO, negrita=True)

    def panel_final(self, lienzo: np.ndarray, guia: Guia, ahora: float) -> None:
        cx, cy = config.ANCHO // 2, 300
        caja(lienzo, cx - 290, cy - 150, cx + 290, cy + 150, FONDO_PANEL, 0.92, 26)
        escribir(lienzo, "¡Canción completada!", cx, cy - 128, 36, BLANCO, "centro", True)
        for k in range(3):
            _estrella(lienzo, cx + (k - 1) * 84, cy - 28, 34, DORADO if k < guia.estrellas else APAGADO)
        resumen = "Precisión %d %%   ·   Tiempo %d s   ·   Mejor racha %d" % (
            round(guia.precision * 100), round(guia.duracion(ahora)), guia.mejor_racha)
        escribir(lienzo, resumen, cx, cy + 36, 21, BLANCO, "centro")
        escribir(lienzo, "R o puño 1 s  repetir     ·     S  otra canción     ·     3  modo ritmo",
                 cx, cy + 92, 17, GRIS, "centro")

    def panel_final_ritmo(self, lienzo: np.ndarray, ritmo: Ritmo, correccion: Optional[float] = None) -> None:
        """Resultados del modo Ritmo, con un gráfico de cuánto se adelantó o atrasó cada nota."""
        from .sesion import describir_desfase

        cx, cy = config.ANCHO // 2, 330
        caja(lienzo, cx - 330, cy - 215, cx + 330, cy + 213, FONDO_PANEL, 0.93, 26)
        escribir(lienzo, "¡Canción terminada!", cx, cy - 202, 34, BLANCO, "centro", True)
        # Calificación en grande a la izquierda.
        letra = ritmo.calificacion
        tono = COLOR_NOTA[letra]
        cv2.circle(lienzo, (cx - 215, cy - 75), 62, tono, -1, cv2.LINE_AA)
        escribir(lienzo, letra, cx - 215, cy - 129, 82, TINTA, "centro", True)
        for k in range(5):
            _estrella(lienzo, cx - 40 + k * 62, cy - 118, 24, DORADO if k < ritmo.estrellas else APAGADO)
        escribir(lienzo, "%s puntos" % _miles(ritmo.puntos), cx + 84, cy - 84, 34, BLANCO, "centro", True)
        escribir(lienzo, "Precisión %d %%   ·   Mejor combo %d" % (
            round(ritmo.precision * 100), ritmo.mejor_combo), cx + 84, cy - 33, 19, BLANCO, "centro")
        x = cx - 250
        for grado, etiqueta in (("perfecto", "Perfectas"), ("bien", "Bien"), ("fallo", "Falladas")):
            tono = CARTELES[grado][1]
            cv2.circle(lienzo, (x, cy + 23), 7, tono, -1, cv2.LINE_AA)
            x += 16 + escribir(lienzo, "%s  %d" % (etiqueta, ritmo.conteo[grado]), x + 16, cy + 10, 20, BLANCO)
            x += 44
        self._grafico_punteria(lienzo, ritmo, cx - 290, cy + 62, cx + 290, cy + 140)
        resumen = describir_desfase(ritmo.desfases.values())
        if correccion is not None:
            resumen += "   ·   L  corregir el retraso (%+d ms)" % round(1000 * correccion)
        escribir(lienzo, resumen, cx, cy + 150, 17, BLANCO, "centro")
        escribir(lienzo, "R o puño 1 s  repetir     ·     D  dificultad     ·     S  otra canción",
                 cx, cy + 180, 16, GRIS, "centro")

    def _grafico_punteria(self, lienzo: np.ndarray, ritmo: Ritmo, x0: int, y0: int, x1: int, y1: int) -> None:
        """Una marca por nota: arriba = tarde, abajo = temprano; las falladas, en rojo abajo."""
        medio = (y0 + y1) // 2
        escala = (y1 - y0) / 2.0 / ritmo.v_bien
        alto_perfecto = int(ritmo.v_perfecto * escala)
        caja(lienzo, x0, y0, x1, y1, (55, 45, 40), 0.9, 6)
        caja(lienzo, x0, medio - alto_perfecto, x1, medio + alto_perfecto, (70, 90, 95), 0.9)
        cv2.line(lienzo, (x0, medio), (x1, medio), GRIS, 1, cv2.LINE_AA)
        escribir(lienzo, "tarde", x0 - 8, y0 - 4, 12, GRIS, "der")
        escribir(lienzo, "temprano", x0 - 8, y1 - 14, 12, GRIS, "der")
        n = max(len(ritmo.estados) - 1, 1)
        for i, estado in enumerate(ritmo.estados):
            x = int(x0 + 6 + (x1 - x0 - 12) * i / n)
            if estado == "fallo":
                cv2.line(lienzo, (x, y1 - 7), (x, y1 - 1), ROJO, 2, cv2.LINE_AA)
            elif i in ritmo.desfases:
                y = int(np.clip(medio - ritmo.desfases[i] * escala, y0 + 3, y1 - 3))
                cv2.circle(lienzo, (x, y), 3, CARTELES[estado][1], -1, cv2.LINE_AA)

    def espectro(self, lienzo: np.ndarray, niveles: np.ndarray,
                 pico: Optional[Tuple[float, str]]) -> None:
        """Panel del análisis de Fourier: barras por banda de frecuencia y nota dominante."""
        x0, y0, x1, y1 = 14, 122, 330, 250
        caja(lienzo, x0, y0, x1, y1, FONDO_PANEL, 0.8, 14)
        escribir(lienzo, "Espectro (FFT)", x0 + 14, y0 + 8, 15, BLANCO, negrita=True)
        texto = "%s  ·  %d Hz" % (pico[1], round(pico[0])) if pico else "silencio"
        escribir(lienzo, texto, x1 - 14, y0 + 8, 15, DORADO if pico else GRIS, "der", True)
        bx0, by1, alto = x0 + 14, y1 - 22, 70
        ancho_barra = (x1 - x0 - 28) / float(len(niveles))
        for b, nivel in enumerate(niveles):
            if nivel > 0.02:
                bx = int(bx0 + b * ancho_barra)
                tono = _TONO_ESPECTRO[min(int(nivel * len(_TONO_ESPECTRO)), len(_TONO_ESPECTRO) - 1)]
                caja(lienzo, bx, by1 - int(alto * nivel), bx + max(int(ancho_barra) - 1, 1), by1, tono)
        for frecuencia, etiqueta in ((110, "110"), (220, "220"), (440, "440"), (880, "880"), (1760, "1760 Hz")):
            fraccion = np.log(frecuencia / 90.0) / np.log(2200.0 / 90.0)
            escribir(lienzo, etiqueta, bx0 + fraccion * (x1 - x0 - 28), by1 + 3, 11, GRIS, "centro")

    def progreso_puno(self, lienzo: np.ndarray, centro: Tuple[float, float], progreso: float) -> None:
        """Anillo que se completa mientras se mantiene el puño cerrado."""
        x, y = int(centro[0]), int(centro[1])
        cv2.circle(lienzo, (x, y), 46, FONDO_PANEL, 6, cv2.LINE_AA)
        cv2.ellipse(lienzo, (x, y), (46, 46), -90, 0, 360 * progreso, DORADO, 6, cv2.LINE_AA)
        escribir(lienzo, "repetir", x, y + 52, 15, BLANCO, "centro", True)

    def indicador_grabacion(self, lienzo: np.ndarray, segundos: float, ahora: float) -> None:
        """Punto rojo parpadeante y tiempo grabado (no aparece en el propio vídeo)."""
        cadena = "REC  %d:%02d" % (segundos // 60, segundos % 60)
        ancho = medir(cadena, 16, True)[0]
        x0, y0 = config.ANCHO - ancho - 70, config.ALTO - 44
        caja(lienzo, x0, y0, config.ANCHO - 16, y0 + 32, FONDO_PANEL, 0.85, 16)
        if int(ahora * 2) % 2 == 0:
            cv2.circle(lienzo, (x0 + 22, y0 + 16), 8, ROJO, -1, cv2.LINE_AA)
        escribir(lienzo, cadena, x0 + 38, y0 + 5, 16, BLANCO, negrita=True)

    def ayuda(self, lienzo: np.ndarray) -> None:
        x0, y0, x1 = 230, 78, config.ANCHO - 230
        paso = 27
        caja(lienzo, x0, y0, x1, y0 + 30 + paso * len(AYUDA), FONDO_PANEL, 0.94, 24)
        y = y0 + 16
        for tecla, descripcion in AYUDA:
            if not descripcion:
                escribir(lienzo, tecla, x0 + 30, y, 19, DORADO, negrita=True)
            elif not tecla:
                escribir(lienzo, descripcion, x0 + 30, y + 2, 16, BLANCO)
            else:
                escribir(lienzo, tecla, x0 + 30, y + 2, 16, BLANCO, negrita=True)
                escribir(lienzo, descripcion, x0 + 220, y + 2, 16, (215, 215, 215))
            y += paso
