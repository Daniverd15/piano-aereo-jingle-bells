"""Datos de cada interpretación: una fila por nota tocada, exportable a CSV.

Al terminar una canción en Guía o Ritmo se guarda un CSV en ``grabaciones/``
que se puede analizar con ``scripts/analizar_sesion.py`` (o con pandas, Excel,
etc.). Con los desfases del modo Ritmo, además, se estima si la persona toca
sistemáticamente tarde o temprano, y en cuánto, para corregir el retraso.
"""

from __future__ import annotations

import csv
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np

from . import config

CARPETA = config.RAIZ / "grabaciones"
MIN_MUESTRAS = 10  # notas acertadas necesarias para sugerir una corrección
UMBRAL_CORRECCION = 0.025  # s: por debajo, el desfase medio no merece corrección


@dataclass
class Fila:
    """Una nota tocada por la persona."""

    segundo: float  # desde que empezó la canción
    modo: str
    forma: str  # "apuntar" o "cinco dedos"
    mano: str  # "izq", "der" o "teclado"
    dedo: str
    nota_tocada: str
    nota_esperada: str
    resultado: str  # acierto, error, perfecto, bien, sobra (Ritmo: no correspondía a ninguna nota) o libre
    desfase_ms: Optional[float]  # Ritmo: + tarde, - temprano
    fuerza: float


class Sesion:
    def __init__(self) -> None:
        self.filas: List[Fila] = []
        self.t0: Optional[float] = None

    def reiniciar(self, t0: float) -> None:
        self.filas = []
        self.t0 = t0

    def anotar(self, t: float, **datos) -> None:
        if self.t0 is None:
            self.t0 = t
        self.filas.append(Fila(segundo=round(t - self.t0, 3), **datos))

    def guardar(self, cancion: str, carpeta: Optional[Path] = None) -> Path:
        """Escribe el CSV (separado por comas, UTF-8 con BOM para que Excel lo abra bien)."""
        carpeta = carpeta if carpeta is not None else CARPETA
        carpeta.mkdir(parents=True, exist_ok=True)
        modo = self.filas[0].modo if self.filas else "sesion"
        ruta = carpeta / time.strftime("datos_%Y-%m-%d_%H-%M-%S_" + modo + ".csv")
        nombres = [f.name for f in fields(Fila)]
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=["cancion"] + nombres)
            escritor.writeheader()
            for fila in self.filas:
                escritor.writerow(dict(cancion=cancion, **asdict(fila)))
        return ruta


def correccion_sugerida(desfases: Iterable[float]) -> Optional[float]:
    """Retraso adicional (s) que centraría los toques, o ``None`` si no hace falta.

    Se usa la mediana y no la media: un toque muy desviado (por ejemplo, uno
    que se adelantó a propósito) no debe arrastrar la corrección.
    """
    valores = np.asarray(list(desfases), dtype=float)
    if len(valores) < MIN_MUESTRAS:
        return None
    mediana = float(np.median(valores))
    return mediana if abs(mediana) >= UMBRAL_CORRECCION else None


def describir_desfase(desfases: Iterable[float]) -> str:
    """Frase corta sobre la puntería temporal: «a tiempo», «42 ms tarde»…"""
    valores = np.asarray(list(desfases), dtype=float)
    if not len(valores):
        return "Sin notas acertadas"
    mediana = 1000 * float(np.median(valores))
    if abs(mediana) < 1000 * UMBRAL_CORRECCION:
        return "Tocas a tiempo (mediana %+d ms)" % round(mediana)
    return "En general tocas %d ms %s" % (round(abs(mediana)), "tarde" if mediana > 0 else "temprano")
