"""Cámara y seguimiento de manos con MediaPipe, en un hilo propio.

La captura y la red neuronal corren separadas del bucle de dibujo: así la
interfaz nunca se congela esperando a la cámara y siempre se procesa el
fotograma más reciente.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from . import config

# Silencia los avisos internos de MediaPipe/TensorFlow en la consola.
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

log = logging.getLogger(__name__)

# Pares de puntos que forman el esqueleto de la mano (índices de MediaPipe).
CONEXIONES = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)


def asegurar_modelo(ruta: Path = config.RUTA_MODELO) -> Path:
    """Devuelve la ruta del modelo de manos; lo descarga si no está."""
    if not ruta.exists():
        log.info("Descargando el modelo de manos de MediaPipe...")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(config.URL_MODELO, str(ruta))
    return ruta


class Rastreador:
    """Envoltorio de ``HandLandmarker`` (API Tasks de MediaPipe) en modo vídeo."""

    def __init__(self, max_manos: int = 2) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        opciones = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(asegurar_modelo())),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=max_manos,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._mp = mp
        self._detector = mp_vision.HandLandmarker.create_from_options(opciones)
        self._ultimo_ms = -1

    def detectar(self, bgr: np.ndarray, t: float, ancho: int, alto: int) -> List[np.ndarray]:
        """Manos del fotograma como arrays ``(21, 2)`` en píxeles de ``ancho x alto``."""
        rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        imagen = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        # MediaPipe exige marcas de tiempo estrictamente crecientes.
        self._ultimo_ms = max(self._ultimo_ms + 1, int(t * 1000))
        resultado = self._detector.detect_for_video(imagen, self._ultimo_ms)
        return [
            np.array([[punto.x * ancho, punto.y * alto] for punto in mano], dtype=np.float64)
            for mano in resultado.hand_landmarks
        ]

    def cerrar(self) -> None:
        self._detector.close()


def recortar(cuadro: np.ndarray, proporcion: float) -> np.ndarray:
    """Recorta el centro del fotograma a la proporción ancho/alto pedida."""
    alto, ancho = cuadro.shape[:2]
    if ancho / float(alto) > proporcion:
        nuevo = int(round(alto * proporcion))
        x0 = (ancho - nuevo) // 2
        return cuadro[:, x0:x0 + nuevo]
    nuevo = int(round(ancho / proporcion))
    y0 = (alto - nuevo) // 2
    return cuadro[y0:y0 + nuevo]


class Cuadro:
    """Un fotograma ya procesado: imagen, manos e instante de captura."""

    __slots__ = ("imagen", "manos", "t", "numero")

    def __init__(self, imagen: np.ndarray, manos: List[np.ndarray], t: float, numero: int) -> None:
        self.imagen, self.manos, self.t, self.numero = imagen, manos, t, numero


class Vision(threading.Thread):
    """Hilo que captura la cámara, la pone en espejo y localiza las manos.

    Si la cámara no abre, deja de enviar imagen o se desconecta, el hilo no
    muere: anota el problema en ``error`` y vuelve a intentarlo cada pocos
    segundos. En cuanto la cámara responde, ``error`` vuelve a ``None``.
    """

    REINTENTO = 2.0  # s entre intentos de reabrir la cámara
    FALLOS_SEGUIDOS = 60  # lecturas fallidas seguidas antes de reabrir

    def __init__(self, camara: int = 0, espejo: bool = True) -> None:
        super().__init__(name="vision", daemon=True)
        self.camara = camara
        self.espejo = espejo
        self.error: Optional[str] = None
        self.lista = False
        self.fps = 0.0
        self.brillo = 255.0  # brillo medio de la imagen, de 0 a 255
        self._ultimo: Optional[Cuadro] = None
        self._nuevo = threading.Event()
        self._parar = threading.Event()

    def run(self) -> None:
        try:
            rastreador = Rastreador()
        except Exception as exc:  # sin modelo no hay nada que reintentar
            log.exception("No se pudo cargar el detector de manos")
            self.error = "no se pudo cargar el detector de manos: %s" % exc
            return
        try:
            while not self._parar.is_set():
                try:
                    self._capturar(rastreador)
                except Exception as exc:
                    log.warning("Cámara: %s. Reintentando en %.0f s", exc, self.REINTENTO)
                    self.error, self.lista = str(exc), False
                    self._parar.wait(self.REINTENTO)
        finally:
            rastreador.cerrar()

    def _abrir(self):
        """Abre la cámara probando los controladores disponibles."""
        # DirectShow abre mucho más rápido en Windows y entrega siempre el
        # último fotograma; Media Foundation queda de respaldo.
        apis = (cv2.CAP_DSHOW, cv2.CAP_MSMF) if sys.platform == "win32" else (cv2.CAP_ANY,)
        for api in apis:
            captura = cv2.VideoCapture(self.camara, api)
            if captura.isOpened():
                captura.set(cv2.CAP_PROP_FRAME_WIDTH, config.ANCHO)
                captura.set(cv2.CAP_PROP_FRAME_HEIGHT, config.ALTO)
                captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok, _ = captura.read()
                if ok:
                    log.info("Cámara %d abierta (controlador %s)", self.camara, captura.getBackendName())
                    return captura
            captura.release()
        raise RuntimeError("no se pudo abrir la cámara %d" % self.camara)

    def _capturar(self, rastreador: Rastreador) -> None:
        captura = self._abrir()
        try:
            numero, fallos, anterior = 0, 0, time.perf_counter()
            while not self._parar.is_set():
                ok, cuadro = captura.read()
                if not ok or cuadro is None:
                    fallos += 1
                    if fallos > self.FALLOS_SEGUIDOS:
                        raise RuntimeError("la cámara dejó de enviar imagen")
                    time.sleep(0.01)
                    continue
                fallos = 0
                t = time.perf_counter()
                cuadro = recortar(cuadro, config.ANCHO / float(config.ALTO))
                if self.espejo:
                    cuadro = cv2.flip(cuadro, 1)
                self.brillo = float(cuadro[::16, ::16].mean())
                manos = rastreador.detectar(cuadro, t, config.ANCHO, config.ALTO)
                numero += 1
                self._ultimo = Cuadro(cuadro, manos, t, numero)
                self._nuevo.set()
                ahora = time.perf_counter()
                self.fps = 0.9 * self.fps + 0.1 / max(ahora - anterior, 1e-3)
                anterior = ahora
                self.error, self.lista = None, True
        finally:
            captura.release()

    @property
    def oscura(self) -> bool:
        """La cámara funciona pero entrega imagen negra (tapa cerrada o cámara ocupada)."""
        return self.lista and self.brillo < 12.0

    def esperar(self, segundos: float) -> Optional[Cuadro]:
        """Espera un fotograma nuevo; devuelve ``None`` si no llega a tiempo."""
        if not self._nuevo.wait(segundos):
            return None
        self._nuevo.clear()
        return self._ultimo

    def detener(self) -> None:
        self._parar.set()
        if self.is_alive():
            self.join(timeout=3.0)
