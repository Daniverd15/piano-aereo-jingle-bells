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


# Acompañamiento: por acorde, (bajo, quinta, tríada).
ACORDES = {
    "C": ("C3", "G2", ("E3", "G3", "C4")),
    "F": ("F2", "C3", ("F3", "A3", "C4")),
    "G": ("G2", "D3", ("G3", "B3", "D4")),
    "D": ("D3", "A2", ("F#3", "A3", "D4")),
}


def cascabel(fm: int, duracion: float = 0.16) -> np.ndarray:
    """Golpe de cascabeles: parciales agudos no armónicos más ruido."""
    azar = np.random.default_rng(3)
    t = np.arange(int(fm * duracion)) / fm
    onda = 0.8 * azar.standard_normal(len(t))
    for frec in (2700.0, 3400.0, 4300.0, 5200.0, 6100.0, 7300.0):
        if frec < fm / 2.2:
            onda += np.sin(2.0 * np.pi * frec * t + azar.uniform(0, 6.28))
    onda *= np.exp(-28.0 * t) * (0.6 + 0.4 * np.sin(2.0 * np.pi * 38.0 * t) ** 2)
    return (onda / np.max(np.abs(onda))).astype(np.float32)


def clic(fm: int) -> np.ndarray:
    """Golpe seco para la cuenta atrás."""
    t = np.arange(int(fm * 0.06)) / fm
    return (np.sin(2.0 * np.pi * 1200.0 * t) * np.exp(-60.0 * t)).astype(np.float32)


def acompanamiento(cancion, bpm: float, fm: int, entrada: float = 4.0,
                   melodia: Optional[str] = None, fondo: bool = True) -> np.ndarray:
    """Renderiza la pista de fondo completa de una canción como onda mono.

    Empieza ``entrada`` pulsos antes de la primera nota, con un clic por
    pulso como cuenta atrás. Con ``fondo`` añade bajo alternado, acordes y
    cascabeles; con ``melodia`` (un timbre) añade también la melodía. Al ser
    una sola onda, todo queda sincronizado con precisión de muestra.
    """
    seg_pulso = 60.0 / bpm
    pista = np.zeros(int((entrada + cancion.pulsos_totales + 3.0) * seg_pulso * fm), dtype=np.float32)
    cache: Dict[Hashable, np.ndarray] = {}

    def nota(nombre: str, timbre: str, segundos: float) -> np.ndarray:
        clave = (nombre, timbre, round(segundos, 3))
        if clave not in cache:
            onda = sintetizar(frecuencia(nombre), timbre, fm, min(segundos + 0.4, config.DURACION_NOTA))
            corte = min(int(segundos * fm), len(onda))
            onda[corte:] *= np.exp(-np.arange(len(onda) - corte) / (fm * 0.08)).astype(np.float32)
            cache[clave] = onda
        return cache[clave]

    def poner(onda: np.ndarray, pulso: float, ganancia: float) -> None:
        i = int(round((pulso + entrada) * seg_pulso * fm))
        n = min(len(onda), len(pista) - i)
        if i >= 0 and n > 0:
            pista[i:i + n] += ganancia * onda[:n]

    golpe = clic(fm)
    for k in range(int(entrada)):
        poner(golpe, k - entrada, 0.5)
    if fondo:
        campanas = cascabel(fm)
        for pulso in range(int(cancion.pulsos_totales)):
            poner(campanas, pulso, 0.15)
            poner(campanas, pulso + 0.5, 0.07)
        for compas, acorde in enumerate(cancion.acordes):
            bajo, quinta, triada = ACORDES[acorde]
            poner(nota(bajo, "piano", 1.6 * seg_pulso), 4 * compas, 0.36)
            poner(nota(quinta, "piano", 1.6 * seg_pulso), 4 * compas + 2, 0.30)
            for tiempo in (1, 3):
                for nombre in triada:
                    poner(nota(nombre, "piano", 0.5 * seg_pulso), 4 * compas + tiempo, 0.10)
    if melodia:
        for n in cancion.notas:
            poner(nota(n.nota, melodia, n.pulsos * seg_pulso * 0.92), n.inicio, 0.75)
    return pista


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
        self.latencia = 0.0  # s que tarda el sonido en salir por los altavoces
        self._candado = threading.Lock()
        self._voces: Dict[Hashable, _Voz] = {}
        self._colas: List[_Voz] = []  # voces soltadas que aún se apagan
        self._flujo = None
        self._activo = activo
        self._t_revision = 0.0
        self._fallos_callback = 0
        self.toma: Optional[List[np.ndarray]] = None  # bloques de salida mientras se graba
        self._recientes = np.zeros(4096, dtype=np.float32)  # últimas muestras, para el espectro
        if activo:
            self._abrir()
        self._sintetizar_muestras()

    def _sintetizar_muestras(self) -> None:
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
            self.latencia = float(flujo.latency)
            log.info("Audio listo: %d Hz, latencia %.0f ms", fm, flujo.latency * 1000)
            return
        log.warning("No hay salida de audio: la aplicación seguirá sin sonido")

    def _callback(self, salida, cuadros, _tiempo, _estado) -> None:  # pragma: no cover
        # Un error aquí detendría el sonido para siempre: se sustituye por
        # silencio y se anota, pero el flujo sigue vivo.
        try:
            salida[:] = self.mezclar(cuadros)
        except Exception:
            salida.fill(0)
            self._fallos_callback += 1
            if self._fallos_callback <= 3:
                log.exception("Error al mezclar el audio")

    def vigilar(self, ahora: float) -> bool:
        """Reabre la salida de audio si se perdió (p. ej. al desconectar unos audífonos).

        Se llama en cada fotograma pero solo comprueba cada 3 s. Devuelve
        ``True`` si se reabrió con otra frecuencia de muestreo, en cuyo caso las
        ondas ya renderizadas para la frecuencia anterior dejan de servir.
        """
        if not self._activo or ahora - self._t_revision < 3.0:
            return False
        self._t_revision = ahora
        try:
            vivo = self._flujo is not None and self._flujo.active
        except Exception:
            vivo = False
        if vivo:
            return False
        log.warning("La salida de audio no responde: reabriendo")
        self.cerrar()
        self.disponible = False
        anterior = self.fm
        self._abrir()
        if self.fm == anterior:
            return False
        self.silenciar()
        self._sintetizar_muestras()
        return True

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
            # Las voces cuya muestra ya terminó no suenan: se retiran.
            if any(v.pos >= len(v.muestra) for v in self._voces.values()):
                self._voces = {k: v for k, v in self._voces.items() if v.pos < len(v.muestra)}
        # tanh actúa de limitador suave: los acordes no saturan con chasquidos.
        salida = np.tanh(mezcla * self.volumen)
        toma = self.toma
        if toma is not None:
            toma.append(salida.copy())
        # Se sustituye el arreglo entero (no se modifica): leerlo desde otro hilo es seguro.
        n = len(self._recientes)
        self._recientes = np.concatenate((self._recientes, salida.mean(axis=1)))[-n:]
        return salida

    def recientes(self) -> np.ndarray:
        """Las últimas muestras que salieron por los altavoces (mono)."""
        return self._recientes

    # ------------------------------------------------------------------ notas
    def tocar(self, voz: Hashable, nota: str, fuerza: float = 0.8, paneo: float = 0.0,
              timbre: Optional[str] = None) -> None:
        """Hace sonar ``nota`` en la voz indicada (una voz = un dedo)."""
        muestra = self._muestras.get((timbre or self.timbre, nota))
        if muestra is None:
            return
        angulo = (float(np.clip(paneo, -1.0, 1.0)) + 1.0) * np.pi / 4.0
        fuerza = float(np.clip(fuerza, 0.0, 1.0))
        nueva = _Voz(muestra, fuerza * float(np.cos(angulo)), fuerza * float(np.sin(angulo)))
        with self._candado:
            self._apagar(voz, tau=0.03)
            self._voces[voz] = nueva

    def tocar_onda(self, voz: Hashable, onda: np.ndarray, ganancia: float = 1.0) -> None:
        """Reproduce una onda mono ya renderizada (p. ej. el acompañamiento)."""
        nueva = _Voz(onda, ganancia * 0.7071, ganancia * 0.7071)
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
