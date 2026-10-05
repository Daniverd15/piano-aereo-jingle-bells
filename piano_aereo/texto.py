"""Texto con tildes y eñes sobre imágenes de OpenCV.

``cv2.putText`` solo dibuja ASCII, así que cada texto se rasteriza una vez
con Pillow como máscara de transparencia y se guarda en caché.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FUENTES = {
    False: ("segoeui.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttc", "DejaVuSans.ttf"),
    True: ("segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf", "Helvetica.ttc", "DejaVuSans-Bold.ttf"),
}


@lru_cache(maxsize=64)
def _fuente(tam: int, negrita: bool):
    for nombre in _FUENTES[negrita]:
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(tam)
    except TypeError:  # Pillow < 10.1 no admite tamaño
        return ImageFont.load_default()


@lru_cache(maxsize=1024)
def _mascara(cadena: str, tam: int, negrita: bool) -> np.ndarray:
    fuente = _fuente(tam, negrita)
    x0, _, x1, _ = fuente.getbbox(cadena)
    try:
        subida, bajada = fuente.getmetrics()
    except AttributeError:
        subida, bajada = tam, tam // 4
    imagen = Image.new("L", (max(1, x1 - x0 + 2), subida + bajada), 0)
    ImageDraw.Draw(imagen).text((1 - x0, 0), cadena, fill=255, font=fuente)
    return np.asarray(imagen, dtype=np.uint16)


def medir(cadena: str, tam: int = 20, negrita: bool = False) -> Tuple[int, int]:
    """Ancho y alto en píxeles que ocupará el texto."""
    alto, ancho = _mascara(cadena, tam, negrita).shape
    return ancho, alto


def escribir(
    img: np.ndarray,
    cadena: str,
    x: float,
    y: float,
    tam: int = 20,
    color: Tuple[int, int, int] = (255, 255, 255),
    ancla: str = "izq",
    negrita: bool = False,
    opacidad: float = 1.0,
) -> int:
    """Dibuja el texto con su esquina superior en ``(x, y)`` y devuelve su ancho.

    ``ancla`` indica qué parte del texto cae en ``x``: ``izq``, ``centro`` o ``der``.
    """
    if not cadena:
        return 0
    mascara = _mascara(cadena, tam, negrita)
    alto, ancho = mascara.shape
    x = int(round(x - (ancho / 2.0 if ancla == "centro" else ancho if ancla == "der" else 0)))
    y = int(round(y))
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + ancho, img.shape[1]), min(y + alto, img.shape[0])
    if x0 >= x1 or y0 >= y1:
        return ancho
    alfa = mascara[y0 - y:y1 - y, x0 - x:x1 - x, None]
    if opacidad < 1.0:
        alfa = (alfa * opacidad).astype(np.uint16)
    zona = img[y0:y1, x0:x1]
    tinta = np.array(color, dtype=np.uint16)
    zona[:] = ((zona * (255 - alfa) + tinta * alfa) // 255).astype(np.uint8)
    return ancho
