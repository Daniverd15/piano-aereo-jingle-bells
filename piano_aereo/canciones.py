"""Partitura de Jingle Bells y la lógica de los modos Guía y Demo.

La melodía (James Pierpont, 1857) es de dominio público. Está escrita en Do
mayor: el coro usa solo Do-Sol (cinco dedos de una mano) y la estrofa baja
hasta el Sol grave.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class NotaCancion:
    nota: str
    pulsos: float
    silaba: str
    inicio: float  # pulso en el que empieza, contado desde el inicio


class Cancion:
    """Secuencia de notas agrupadas en frases (una frase = una línea de letra).

    Cada frase es un texto ``"NOTA:pulsos:sílaba ..."``. Una sílaba terminada
    en ``-`` se une a la siguiente al mostrar la letra.
    """

    def __init__(self, nombre: str, bpm: float, frases: Sequence[str]) -> None:
        self.nombre = nombre
        self.bpm = bpm
        self.notas: List[NotaCancion] = []
        self.frases: List[Tuple[int, int]] = []
        pulso = 0.0
        for frase in frases:
            primero = len(self.notas)
            for ficha in frase.split():
                nota, pulsos, silaba = ficha.split(":", 2)
                self.notas.append(NotaCancion(nota, float(pulsos), silaba, pulso))
                pulso += float(pulsos)
            self.frases.append((primero, len(self.notas)))
        self.pulsos_totales = pulso

    def __len__(self) -> int:
        return len(self.notas)

    def frase_de(self, indice: int) -> Tuple[int, int]:
        """Rango ``[inicio, fin)`` de la frase que contiene la nota ``indice``."""
        for primero, fin in self.frases:
            if indice < fin:
                return primero, fin
        return self.frases[-1]


_OH_WHAT_FUN = "F4:1:Oh F4:1:what F4:1.5:fun F4:0.5:it F4:1:is E4:1:to E4:1:ride E4:0.5:in E4:0.5:a"

_CORO = (
    "E4:1:Jin- E4:1:gle E4:2:bells,",
    "E4:1:jin- E4:1:gle E4:2:bells,",
    "E4:1:jin- G4:1:gle C4:1.5:all D4:0.5:the E4:4:way!",
    _OH_WHAT_FUN,
    "E4:1:one- D4:1:horse D4:1:o- E4:1:pen D4:2:sleigh, G4:2:hey!",
    "E4:1:Jin- E4:1:gle E4:2:bells,",
    "E4:1:jin- E4:1:gle E4:2:bells,",
    "E4:1:jin- G4:1:gle C4:1.5:all D4:0.5:the E4:4:way!",
    _OH_WHAT_FUN,
    "G4:1:one- G4:1:horse F4:1:o- D4:1:pen C4:4:sleigh!",
)

_ESTROFA = (
    "G3:1:Dash- E4:1:ing D4:1:through C4:1:the G3:3:snow G3:0.5:in G3:0.5:a",
    "G3:1:one- E4:1:horse D4:1:o- C4:1:pen A3:4:sleigh,",
    "A3:1:o'er F4:1:the E4:1:fields D4:1:we B3:4:go,",
    "G4:1:laugh- G4:1:ing F4:1:all D4:1:the E4:4:way.",
    "G3:1:Bells E4:1:on D4:1:bob- C4:1:tails G3:4:ring,",
    "G3:1:mak- E4:1:ing D4:1:spi- C4:1:rits A3:3:bright, A3:1:what",
    "A3:1:fun F4:1:it E4:1:is D4:1:to G4:1:ride G4:1:and G4:1:sing G4:1:a",
    "A4:1:sleigh- G4:1:ing F4:1:song D4:1:to- C4:2:night. G4:2:Oh!",
)

CANCIONES: Dict[str, Cancion] = {
    "coro": Cancion("Jingle Bells (coro)", 132, _CORO),
    "completa": Cancion("Jingle Bells (completa)", 132, _ESTROFA + _CORO),
}


class Guia:
    """Modo Guía: la canción espera a que toques la nota correcta."""

    def __init__(self, cancion: Cancion) -> None:
        self.cancion = cancion
        self.reiniciar()

    def reiniciar(self) -> None:
        self.indice = 0
        self.aciertos = 0
        self.errores = 0
        self.racha = 0
        self.mejor_racha = 0
        self.t_inicio: Optional[float] = None
        self.t_fin: Optional[float] = None

    @property
    def terminada(self) -> bool:
        return self.indice >= len(self.cancion)

    @property
    def objetivo(self) -> Optional[str]:
        return None if self.terminada else self.cancion.notas[self.indice].nota

    @property
    def precision(self) -> float:
        total = self.aciertos + self.errores
        return self.aciertos / float(total) if total else 1.0

    @property
    def estrellas(self) -> int:
        return 3 if self.precision >= 0.9 else 2 if self.precision >= 0.7 else 1

    def duracion(self, ahora: float) -> float:
        if self.t_inicio is None:
            return 0.0
        return (self.t_fin if self.t_fin is not None else ahora) - self.t_inicio

    def pulsar(self, nota: str, ahora: float) -> Optional[bool]:
        """Registra una nota tocada. ``True`` acierto, ``False`` error, ``None`` si ya acabó."""
        if self.terminada:
            return None
        if self.t_inicio is None:
            self.t_inicio = ahora
        if nota == self.objetivo:
            self.indice += 1
            self.aciertos += 1
            self.racha += 1
            self.mejor_racha = max(self.mejor_racha, self.racha)
            if self.terminada:
                self.t_fin = ahora
            return True
        self.errores += 1
        self.racha = 0
        return False


class Demo:
    """Modo Demo: la canción suena sola, a tempo, y se repite."""

    ENTRADA = 3.0  # pulsos de espera antes de la primera nota
    PAUSA = 4.0  # pulsos de silencio antes de repetir
    LEGATO = 0.92  # fracción de la duración que suena cada nota

    def __init__(self, cancion: Cancion, ahora: float) -> None:
        self.cancion = cancion
        self.reiniciar(ahora)

    def reiniciar(self, ahora: float) -> None:
        self.t0 = ahora
        self.indice = 0  # próxima nota por empezar
        self.sonando: List[Tuple[int, float]] = []  # (índice, pulso en que se suelta)

    def pulso(self, ahora: float) -> float:
        return (ahora - self.t0) * self.cancion.bpm / 60.0 - self.ENTRADA

    def actualizar(self, ahora: float) -> Tuple[List[int], List[int]]:
        """Devuelve ``(notas que empiezan, notas que terminan)`` como índices."""
        pulso = self.pulso(ahora)
        notas = self.cancion.notas
        terminan = [i for i, fin in self.sonando if pulso >= fin]
        self.sonando = [(i, fin) for i, fin in self.sonando if pulso < fin]
        empiezan: List[int] = []
        while self.indice < len(notas) and notas[self.indice].inicio <= pulso:
            n = notas[self.indice]
            empiezan.append(self.indice)
            self.sonando.append((self.indice, n.inicio + n.pulsos * self.LEGATO))
            self.indice += 1
        if self.indice >= len(notas) and not self.sonando:
            if pulso >= self.cancion.pulsos_totales + self.PAUSA:
                self.reiniciar(ahora)
        return empiezan, terminan
