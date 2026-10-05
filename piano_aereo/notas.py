"""Teoría musical mínima y geometría del teclado en pantalla."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

_SEMITONOS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SOLFEO = {"C": "Do", "D": "Re", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}
# Un color por nota (BGR), igual en todas las octavas.
_COLORES = {
    "C": (95, 90, 255),
    "D": (28, 159, 255),
    "E": (63, 210, 255),
    "F": (132, 220, 61),
    "G": (241, 196, 46),
    "A": (250, 124, 91),
    "B": (255, 125, 199),
}


def a_midi(nota: str) -> int:
    """``"C4"`` -> 60. Acepta sostenidos y bemoles (``"F#3"``, ``"Bb4"``)."""
    letra, resto = nota[0].upper(), nota[1:]
    if letra not in _SEMITONOS:
        raise ValueError("Nota inválida: %r" % nota)
    alteracion = 0
    while resto and resto[0] in "#b":
        alteracion += 1 if resto[0] == "#" else -1
        resto = resto[1:]
    return 12 * (int(resto) + 1) + _SEMITONOS[letra] + alteracion


def frecuencia(nota: str) -> float:
    """Frecuencia en Hz con temperamento igual (La4 = 440 Hz)."""
    return 440.0 * 2.0 ** ((a_midi(nota) - 69) / 12.0)


def solfeo(nota: str) -> str:
    return _SOLFEO[nota[0].upper()]


def color(nota: str) -> Tuple[int, int, int]:
    return _COLORES[nota[0].upper()]


class Teclado:
    """Teclas blancas repartidas a lo ancho de la pantalla.

    Cada tecla define además un *carril* vertical: la nota que toca un dedo
    depende solo de la posición horizontal de su punta.
    """

    def __init__(self, notas: Sequence[str], x: int, y: int, ancho: int, alto: int) -> None:
        self.notas = tuple(notas)
        self.x, self.y, self.ancho, self.alto = x, y, ancho, alto
        self.ancho_tecla = ancho / float(len(self.notas))

    def __len__(self) -> int:
        return len(self.notas)

    def tecla_en(self, x: float) -> Optional[int]:
        """Índice de la tecla cuyo carril contiene ``x`` (o ``None`` si queda fuera)."""
        if x < self.x or x >= self.x + self.ancho:
            return None
        return min(int((x - self.x) / self.ancho_tecla), len(self.notas) - 1)

    def indice(self, nota: str) -> int:
        return self.notas.index(nota)

    def rect(self, i: int) -> Tuple[int, int, int, int]:
        """Rectángulo ``(x0, y0, x1, y1)`` de la tecla ``i``."""
        x0 = int(round(self.x + i * self.ancho_tecla))
        x1 = int(round(self.x + (i + 1) * self.ancho_tecla))
        return x0, self.y, x1, self.y + self.alto

    def centro(self, i: int) -> int:
        return int(round(self.x + (i + 0.5) * self.ancho_tecla))

    def paneo(self, i: int) -> float:
        """Posición estéreo de la tecla: graves a la izquierda, agudos a la derecha."""
        if len(self.notas) < 2:
            return 0.0
        return (i / (len(self.notas) - 1.0) - 0.5) * 1.2
