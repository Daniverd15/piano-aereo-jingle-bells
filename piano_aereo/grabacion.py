"""Grabación de la interpretación: vídeo de la pantalla y audio de lo que suena.

Sirve como evidencia de la actividad. OpenCV no puede meter audio dentro del
vídeo, así que se guardan dos archivos con el mismo nombre (``.mp4`` y
``.wav``) que empiezan en el mismo instante y se pueden unir en cualquier
editor de vídeo.
"""

from __future__ import annotations

import logging
import time
import wave
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from . import config

log = logging.getLogger(__name__)

CARPETA = config.RAIZ / "grabaciones"


def _nombre(prefijo: str) -> str:
    return time.strftime(prefijo + "_%Y-%m-%d_%H-%M-%S")


def guardar_captura(lienzo: np.ndarray, carpeta: Path = CARPETA) -> Path:
    """Guarda la pantalla actual como PNG y devuelve la ruta."""
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / (_nombre("captura") + ".png")
    if not cv2.imwrite(str(ruta), lienzo):
        raise OSError("no se pudo escribir %s" % ruta)
    return ruta


class Grabadora:
    """Graba el lienzo a 30 fps y el audio del mezclador mientras está activa."""

    FPS = 30

    def __init__(self, carpeta: Path = CARPETA) -> None:
        self.carpeta = carpeta
        self._video = None
        self._audio = None
        self._base: Optional[Path] = None
        self._t0 = 0.0
        self._escritos = 0

    @property
    def activa(self) -> bool:
        return self._video is not None

    def duracion(self, ahora: float) -> float:
        return ahora - self._t0 if self.activa else 0.0

    def iniciar(self, audio, ahora: float) -> Path:
        """Empieza a grabar. ``audio`` es el ``MotorAudio`` cuya salida se guarda."""
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._base = self.carpeta / _nombre("piano")
        video = cv2.VideoWriter(str(self._base.with_suffix(".mp4")), cv2.VideoWriter_fourcc(*"mp4v"),
                                self.FPS, (config.ANCHO, config.ALTO))
        if not video.isOpened():
            raise OSError("no se pudo crear el archivo de vídeo")
        self._video, self._t0, self._escritos = video, ahora, 0
        self._audio = audio if audio.disponible else None
        if self._audio is not None:
            self._audio.toma = []
        return self._base.with_suffix(".mp4")

    def cuadro(self, lienzo: np.ndarray, ahora: float) -> None:
        """Añade el lienzo al vídeo, repitiéndolo si hace falta para ir a tiempo real."""
        if not self.activa:
            return
        objetivo = int((ahora - self._t0) * self.FPS) + 1
        # Si el bucle se atrasó, se repite el fotograma (como mucho medio segundo).
        for _ in range(min(objetivo - self._escritos, self.FPS // 2)):
            self._video.write(lienzo)
        self._escritos = max(self._escritos, objetivo)

    def detener(self) -> List[Path]:
        """Cierra los archivos y devuelve las rutas guardadas."""
        if not self.activa:
            return []
        self._video.release()
        self._video = None
        rutas = [self._base.with_suffix(".mp4")]
        if self._audio is not None:
            bloques, self._audio.toma = self._audio.toma, None
            if bloques:
                muestras = (np.clip(np.concatenate(bloques), -1.0, 1.0) * 32767).astype("<i2")
                ruta = self._base.with_suffix(".wav")
                with wave.open(str(ruta), "wb") as archivo:
                    archivo.setnchannels(2)
                    archivo.setsampwidth(2)
                    archivo.setframerate(self._audio.fm)
                    archivo.writeframes(muestras.tobytes())
                rutas.append(ruta)
        log.info("Grabación guardada: %s", ", ".join(str(r) for r in rutas))
        return rutas
