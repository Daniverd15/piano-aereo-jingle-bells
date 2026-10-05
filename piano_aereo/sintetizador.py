"""Síntesis de las notas y motor de audio polifónico en tiempo real.

No se usa ningún archivo de sonido: cada nota se genera con NumPy (síntesis
aditiva) y se mezcla en el *callback* de ``sounddevice``, lo que da una
latencia mucho menor que reproducir muestras con un mezclador genérico.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, Hashable, List, Optional, Sequence

import numpy as np

from . import config
from .notas import frecuencia

log = logging.getLogger(__name__)

# Parciales de una campana afinada: (razón de frecuencia, amplitud).
_PARCIALES_CAMPANA = (
    (0.5, 0.25), (1.0, 1.0), (1.183, 0.5), (1.506, 0.35), (2.0, 0.6),
    (2.514, 0.2), (2.662, 0.2), (3.011, 0.15), (4.166, 0.1),
)


def sintetizar(
    frec: float,
    timbre: str = "piano",
    fm: int = config.FRECUENCIA_MUESTREO,
    duracion: float = config.DURACION_NOTA,
) -> np.ndarray:
    """Genera una nota como onda mono ``float32`` con pico 0.9."""
    t = np.arange(int(fm * duracion), dtype=np.float64) / fm
    onda = np.zeros_like(t)
    dos_pi = 2.0 * np.pi
    if timbre == "campanas":
        for razon, amp in _PARCIALES_CAMPANA:
            if frec * razon < fm / 2.2:
                onda += amp * np.exp(-(1.2 + 0.8 * razon) * t) * np.sin(dos_pi * frec * razon * t)
    elif timbre == "cajita":
        onda += np.exp(-3.2 * t) * np.sin(dos_pi * frec * t)
        onda += 0.45 * np.exp(-5.0 * t) * np.sin(dos_pi * 2.0 * frec * t)
        onda += 0.25 * np.exp(-9.0 * t) * np.sin(dos_pi * 4.07 * frec * t)
    else:  # piano
        # Los armónicos de una cuerda real son algo más agudos que los
        # múltiplos exactos (inarmonicidad) y los agudos se apagan antes.
        inarmonicidad = 0.0004
        for n in range(1, 10):
            fn = frec * n * np.sqrt(1.0 + inarmonicidad * n * n)
            if fn >= fm / 2.2:
                break
            caida = 1.6 + 0.55 * n + frec / 600.0
            onda += n ** -1.25 * np.exp(-caida * t) * np.sin(dos_pi * fn * t + 0.3 * n)
        onda += 0.25 * np.exp(-0.9 * t) * np.sin(dos_pi * frec * t)
    ataque = max(1, int(0.004 * fm))
    onda[:ataque] *= np.linspace(0.0, 1.0, ataque)
    cola = max(1, int(0.03 * fm))
    onda[-cola:] *= np.linspace(1.0, 0.0, cola)
    return (0.9 * onda / np.max(np.abs(onda))).astype(np.float32)


class _Voz:
    __slots__ = ("muestra", "pos", "izq", "der", "soltando", "ganancia", "tau")

    def __init__(self, muestra: np.ndarray, izq: float, der: float) -> None:
        self.muestra = muestra
        self.pos = 0
        self.izq, self.der = izq, der
        self.soltando = False
        self.ganancia = 1.0
        self.tau = 0.09


class MotorAudio:
    """Mezclador polifónico: una voz por dedo, con apagado suave al soltar."""

    def __init__(
        self,
        notas: Sequence[str],
        timbre: str = "piano",
        volumen: float = config.VOLUMEN,
        activo: bool = True,
    ) -> None:
        self.notas = tuple(notas)
        self.timbre = timbre if timbre in config.TIMBRES else "piano"
        self.volumen = volumen
        self.fm = config.FRECUENCIA_MUESTREO
        self.disponible = False
        self._candado = threading.Lock()
        self._voces: Dict[Hashable, _Voz] = {}
        self._colas: List[_Voz] = []  # voces soltadas que aún se apagan
        self._flujo = None
        if activo:
            self._abrir()
        self._muestras = {
            (timbre, nota): sintetizar(frecuencia(nota), timbre, self.fm)
            for timbre in config.TIMBRES
            for nota in self.notas
        }

    # ------------------------------------------------------------ dispositivo
    def _abrir(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depende del equipo
            log.warning("sounddevice no disponible (%s): sin sonido", exc)
            return
        # WASAPI tiene bastante menos latencia que el controlador por defecto
        # de Windows (MME); si no existe o falla se usa el dispositivo normal.
        candidatos = []
        try:
            for api in sd.query_hostapis():
                if "WASAPI" in api["name"] and api["default_output_device"] >= 0:
                    dispositivo = api["default_output_device"]
                    fm = int(sd.query_devices(dispositivo)["default_samplerate"])
                    candidatos.append((dispositivo, fm))
        except Exception:  # pragma: no cover
            pass
        candidatos.append((None, config.FRECUENCIA_MUESTREO))
        for dispositivo, fm in candidatos:
            try:
                flujo = sd.OutputStream(
                    device=dispositivo, samplerate=fm, channels=2, dtype="float32",
                    latency="low", callback=self._callback,
                )
                flujo.start()
            except Exception as exc:  # pragma: no cover
                log.info("No se pudo abrir la salida %s (%s)", dispositivo, exc)
                continue
            self._flujo, self.fm, self.disponible = flujo, fm, True
            log.info("Audio listo: %d Hz, latencia %.0f ms", fm, flujo.latency * 1000)
            return
        log.warning("No hay salida de audio: la aplicación seguirá sin sonido")

    def _callback(self, salida, cuadros, _tiempo, _estado) -> None:  # pragma: no cover
        salida[:] = self.mezclar(cuadros)

    # ----------------------------------------------------------------- mezcla
    def mezclar(self, cuadros: int) -> np.ndarray:
        """Devuelve el siguiente bloque estéreo ``(cuadros, 2)`` en ``float32``."""
        mezcla = np.zeros((cuadros, 2), dtype=np.float32)
        with self._candado:
            voces = list(self._voces.values()) + self._colas
            for voz in voces:
                trozo = voz.muestra[voz.pos:voz.pos + cuadros]
                n = len(trozo)
                if voz.soltando:
                    curva = voz.ganancia * np.exp(-np.arange(n) / (self.fm * voz.tau))
                    trozo = trozo * curva.astype(np.float32)
                    voz.ganancia = float(curva[-1]) if n else 0.0
                mezcla[:n, 0] += trozo * voz.izq
                mezcla[:n, 1] += trozo * voz.der
                voz.pos += n
            self._colas = [v for v in self._colas if v.pos < len(v.muestra) and v.ganancia > 1e-3]
        # tanh actúa de limitador suave: los acordes no saturan con chasquidos.
        return np.tanh(mezcla * self.volumen)

    # ------------------------------------------------------------------ notas
    def tocar(self, voz: Hashable, nota: str, fuerza: float = 0.8, paneo: float = 0.0) -> None:
        """Hace sonar ``nota`` en la voz indicada (una voz = un dedo)."""
        muestra = self._muestras.get((self.timbre, nota))
        if muestra is None:
            return
        angulo = (float(np.clip(paneo, -1.0, 1.0)) + 1.0) * np.pi / 4.0
        fuerza = float(np.clip(fuerza, 0.0, 1.0))
        nueva = _Voz(muestra, fuerza * float(np.cos(angulo)), fuerza * float(np.sin(angulo)))
        with self._candado:
            self._apagar(voz, tau=0.03)
            self._voces[voz] = nueva

    def soltar(self, voz: Hashable) -> None:
        """Apaga la voz como el apagador de un piano al levantar el dedo."""
        with self._candado:
            self._apagar(voz, tau=0.09)

    def _apagar(self, voz: Hashable, tau: float) -> None:
        anterior = self._voces.pop(voz, None)
        if anterior is not None:
            anterior.soltando, anterior.tau = True, tau
            self._colas.append(anterior)

    def silenciar(self) -> None:
        with self._candado:
            for voz in list(self._voces):
                self._apagar(voz, tau=0.05)

    def siguiente_timbre(self) -> str:
        i = config.TIMBRES.index(self.timbre)
        self.timbre = config.TIMBRES[(i + 1) % len(config.TIMBRES)]
        return self.timbre

    def cerrar(self) -> None:
        if self._flujo is not None:
            try:
                self._flujo.stop()
                self._flujo.close()
            except Exception:  # pragma: no cover
                pass
            self._flujo = None
