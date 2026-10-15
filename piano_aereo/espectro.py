"""Análisis de Fourier del sonido que sale por los altavoces.

Muestra en vivo qué frecuencias suenan y reconoce la nota dominante, para ver
que La4 son 440 Hz y que cada octava duplica la frecuencia.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

F_MIN, F_MAX = 90.0, 2200.0  # Hz representados (de Sol2 a Do#7, aprox.)
BANDAS = 56
RANGO_DB = 60.0  # lo que hay por debajo de -60 dB respecto al máximo posible no se ve

_NOMBRES = ("Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si")


def nombre_nota(frecuencia: float) -> Tuple[str, int]:
    """Nota más cercana a una frecuencia y su desviación en centésimas de semitono."""
    midi = 69.0 + 12.0 * np.log2(frecuencia / 440.0)
    cercana = int(round(midi))
    return "%s%d" % (_NOMBRES[cercana % 12], cercana // 12 - 1), int(round(100 * (midi - cercana)))


def analizar(muestras: np.ndarray, fm: int) -> Tuple[np.ndarray, Optional[Tuple[float, str]]]:
    """Devuelve ``(nivel de cada banda de 0 a 1, (frecuencia, nota) dominante o None)``.

    Las bandas están repartidas en escala logarítmica, como las teclas de un
    piano: cada octava ocupa el mismo ancho.
    """
    n = len(muestras)
    ventana = np.hanning(n)
    # Amplitud de cada sinusoide: la ventana de Hann reduce la ganancia a la mitad.
    amplitud = np.abs(np.fft.rfft(muestras * ventana)) * 2.0 / (n * 0.5)
    frecuencias = np.fft.rfftfreq(n, 1.0 / fm)
    bordes = np.geomspace(F_MIN, F_MAX, BANDAS + 1)
    indices = np.searchsorted(frecuencias, bordes)
    niveles = np.zeros(BANDAS)
    for b in range(BANDAS):
        trozo = amplitud[indices[b]:max(indices[b + 1], indices[b] + 1)]
        if len(trozo):
            db = 20.0 * np.log10(float(trozo.max()) + 1e-9)
            niveles[b] = np.clip((db + RANGO_DB) / RANGO_DB, 0.0, 1.0)

    zona = (frecuencias >= F_MIN) & (frecuencias <= F_MAX)
    if not zona.any():
        return niveles, None
    k = int(np.flatnonzero(zona)[np.argmax(amplitud[zona])])
    if amplitud[k] < 0.005 or k == 0 or k >= len(amplitud) - 1:
        return niveles, None  # silencio
    # Interpolación parabólica del pico: más precisión que el ancho de un bin (~12 Hz).
    a, b, c = np.log(amplitud[k - 1:k + 2] + 1e-12)
    desplazamiento = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    frecuencia = (k + desplazamiento) * fm / n
    return niveles, (float(frecuencia), nombre_nota(frecuencia)[0])
