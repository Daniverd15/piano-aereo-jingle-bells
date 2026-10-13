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

    def __init__(self, nombre: str, bpm: float, frases: Sequence[str], acordes: Sequence[str] = ()) -> None:
        self.nombre = nombre
        self.bpm = bpm
        self.acordes = tuple(acordes)  # un acorde por compás, para el acompañamiento
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

_ACORDES_CORO = ("C", "C", "C", "C", "F", "C", "D", "G", "C", "C", "C", "C", "F", "C", "G", "C")
_ACORDES_ESTROFA = ("C", "C", "C", "F", "F", "G", "G", "C", "C", "C", "C", "F", "F", "C", "G", "C")

CANCIONES: Dict[str, Cancion] = {
    "coro": Cancion("Jingle Bells (coro)", 132, _CORO, _ACORDES_CORO),
    "completa": Cancion("Jingle Bells (completa)", 132, _ESTROFA + _CORO,
                        _ACORDES_ESTROFA + _ACORDES_CORO),
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
    """Modo Demo: la canción suena sola, a tempo."""

    ENTRADA = 4.0  # pulsos de cuenta atrás antes de la primera nota
    PAUSA = 3.0  # pulsos de silencio al acabar
    LEGATO = 0.92  # fracción de la duración que suena cada nota

    def __init__(self, cancion: Cancion, t0: float, bpm: Optional[float] = None) -> None:
        self.cancion = cancion
        self.bpm = bpm or cancion.bpm
        self.t0 = t0
        self.indice = 0  # próxima nota por empezar
        self.sonando: List[Tuple[int, float]] = []  # (índice, pulso en que se suelta)

    def pulso(self, ahora: float) -> float:
        return (ahora - self.t0) * self.bpm / 60.0 - self.ENTRADA

    def terminada(self, ahora: float) -> bool:
        return self.pulso(ahora) >= self.cancion.pulsos_totales + self.PAUSA

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
        return empiezan, terminan


class Ritmo:
    """Modo Ritmo: las notas caen a tempo y hay que tocarlas justo al llegar.

    Cada nota se califica según lo cerca que se tocó de su instante exacto:
    ``perfecto``, ``bien`` o, si se deja pasar, ``fallo``. Las notas seguidas
    forman un combo que multiplica los puntos (hasta x4).
    """

    ENTRADA = 4.0  # pulsos de cuenta atrás
    PUNTOS = {"perfecto": 100, "bien": 60}
    COMBO_POR_NIVEL = 8  # aciertos seguidos para subir el multiplicador
    # Fracción mínima de la puntuación perfecta para cada calificación.
    CALIFICACIONES = ((0.95, "S"), (0.85, "A"), (0.70, "B"), (0.50, "C"), (0.0, "D"))

    def __init__(self, cancion: Cancion, bpm: float, ventanas: Tuple[float, float], t0: float) -> None:
        self.cancion = cancion
        self.bpm = bpm
        self.seg_pulso = 60.0 / bpm
        self.v_perfecto, self.v_bien = ventanas  # tolerancias en segundos
        self.t0 = t0
        self.estados: List[Optional[str]] = [None] * len(cancion)
        self.primera = 0  # primera nota aún sin calificar
        self.puntos = 0
        self.combo = 0
        self.mejor_combo = 0
        self.conteo = {"perfecto": 0, "bien": 0, "fallo": 0}

    def pulso(self, ahora: float) -> float:
        return (ahora - self.t0) / self.seg_pulso - self.ENTRADA

    def instante(self, i: int) -> float:
        """Momento exacto en que debe sonar la nota ``i``."""
        return self.t0 + (self.cancion.notas[i].inicio + self.ENTRADA) * self.seg_pulso

    @property
    def multiplicador(self) -> int:
        return min(4, 1 + self.combo // self.COMBO_POR_NIVEL)

    def candidatas(self, t: float) -> List[int]:
        """Notas sin calificar que se pueden tocar en el instante ``t``."""
        indices = []
        for i in range(self.primera, len(self.estados)):
            instante = self.instante(i)
            if instante > t + self.v_bien:
                break
            if self.estados[i] is None and instante >= t - self.v_bien:
                indices.append(i)
        return indices

    def pulsar(self, nota: str, t: float) -> Optional[Tuple[int, str]]:
        """Registra una nota tocada. Devuelve ``(índice, calificación)`` si acierta."""
        for i in self.candidatas(t):
            if self.cancion.notas[i].nota == nota:
                grado = "perfecto" if abs(self.instante(i) - t) <= self.v_perfecto else "bien"
                self.estados[i] = grado
                self.conteo[grado] += 1
                self.combo += 1
                self.mejor_combo = max(self.mejor_combo, self.combo)
                self.puntos += self.PUNTOS[grado] * self.multiplicador
                return i, grado
        return None

    def actualizar(self, ahora: float) -> List[int]:
        """Marca como falladas las notas que ya pasaron y devuelve sus índices."""
        falladas = []
        while self.primera < len(self.estados):
            if self.estados[self.primera] is None:
                if self.instante(self.primera) >= ahora - self.v_bien:
                    break
                self.estados[self.primera] = "fallo"
                self.conteo["fallo"] += 1
                self.combo = 0
                falladas.append(self.primera)
            self.primera += 1
        return falladas

    def terminada(self, ahora: float) -> bool:
        return self.primera >= len(self.estados) and self.pulso(ahora) >= self.cancion.pulsos_totales + 1.0

    @property
    def aciertos(self) -> int:
        return self.conteo["perfecto"] + self.conteo["bien"]

    @property
    def precision(self) -> float:
        """Puntuación obtenida frente a tocarlo todo perfecto, sin contar el combo."""
        ideal = self.PUNTOS["perfecto"] * len(self.estados)
        logrado = sum(self.PUNTOS[g] * self.conteo[g] for g in self.PUNTOS)
        return logrado / float(ideal) if ideal else 0.0

    @property
    def calificacion(self) -> str:
        return next(letra for minimo, letra in self.CALIFICACIONES if self.precision >= minimo)

    @property
    def estrellas(self) -> int:
        return 5 - "SABCD".index(self.calificacion)
