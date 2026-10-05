"""Bucle principal: une visión, detección de toques, audio, canción e interfaz."""

from __future__ import annotations

import argparse
import logging
import time
from typing import Dict, Hashable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import config
from .canciones import CANCIONES, Demo, Guia
from .interfaz import Interfaz
from .notas import Teclado
from .sintetizador import MotorAudio
from .toques import DetectorToques

log = logging.getLogger(__name__)

MODOS = ("libre", "guia", "demo")
_ESC = 27


class App:
    def __init__(self, args: argparse.Namespace) -> None:
        self.teclado = Teclado(
            config.NOTAS_TECLADO, config.TECLADO_MARGEN, config.TECLADO_Y,
            config.ANCHO - 2 * config.TECLADO_MARGEN, config.TECLADO_ALTO,
        )
        self.interfaz = Interfaz(self.teclado)
        self.detector = DetectorToques(args.sensibilidad)
        self.audio = MotorAudio(self.teclado.notas, args.timbre, activo=not args.sin_sonido)
        self.sin_camara = args.sin_camara
        self.vision = None
        if not self.sin_camara:
            from .vision import Vision

            self.vision = Vision(args.camara, espejo=not args.sin_espejo)
        self.pantalla_completa = args.pantalla_completa

        self.cancion_id = args.cancion
        self.modo = "libre"
        self.guia = Guia(CANCIONES[self.cancion_id])
        self.demo = Demo(CANCIONES[self.cancion_id], 0.0)
        self.pulso_vis = 0.0
        self.pulsadas: Dict[Hashable, int] = {}  # voz -> tecla que mantiene pulsada
        self.fallos: Dict[int, float] = {}  # tecla -> instante del último error
        self.notas_pc: List[Tuple[Hashable, float]] = []  # (voz, instante de soltar)
        self.ver_ayuda = False
        self.ver_esqueleto = True
        self._aviso: Tuple[str, float] = ("", 0.0)
        self._imagen: Optional[np.ndarray] = None
        self._manos: Sequence[np.ndarray] = ()
        self._t_manos = 0.0
        self._t_dibujo: Optional[float] = None
        self.cambiar_modo(args.modo, time.perf_counter())

    # ----------------------------------------------------------------- estado
    @property
    def cancion(self):
        return CANCIONES[self.cancion_id]

    def avisar(self, cadena: str, ahora: float, segundos: float = 2.0) -> None:
        self._aviso = (cadena, ahora + segundos)

    def cambiar_modo(self, modo: str, ahora: float) -> None:
        self.modo = modo
        self.audio.silenciar()
        self.pulsadas.clear()
        self.fallos.clear()
        self.guia = Guia(self.cancion)
        self.demo = Demo(self.cancion, ahora)
        self.pulso_vis = -Demo.ENTRADA if modo == "demo" else 0.0

    def tocar(self, voz: Hashable, tecla: int, fuerza: float, ahora: float, del_usuario: bool = True) -> None:
        nota = self.teclado.notas[tecla]
        self.audio.tocar(voz, nota, fuerza, self.teclado.paneo(tecla))
        self.pulsadas[voz] = tecla
        self.interfaz.chispear(tecla)
        if del_usuario and self.modo == "guia" and self.guia.pulsar(nota, ahora) is False:
            self.fallos[tecla] = ahora

    def soltar(self, voz: Hashable) -> None:
        self.audio.soltar(voz)
        self.pulsadas.pop(voz, None)

    # ----------------------------------------------------------------- lógica
    def procesar_manos(self, manos: Sequence[np.ndarray], t: float) -> None:
        """Pasa las manos de un fotograma por el detector y hace sonar los toques."""
        self._manos = manos
        if manos:
            self._t_manos = t
        for toque in self.detector.actualizar(manos, t):
            if not toque.pulsa:
                self.soltar(toque.voz)
                continue
            tecla = self.teclado.tecla_en(toque.x)
            if tecla is not None:
                self.tocar(toque.voz, tecla, toque.fuerza, t)

    def avanzar(self, ahora: float, dt: float) -> None:
        """Lógica que depende del tiempo y no de la cámara."""
        for voz, t_fin in list(self.notas_pc):
            if ahora >= t_fin:
                self.soltar(voz)
                self.notas_pc.remove((voz, t_fin))
        if self.modo == "demo":
            empiezan, terminan = self.demo.actualizar(ahora)
            for i in terminan:
                self.soltar(("demo", i))
            for i in empiezan:
                tecla = self.teclado.indice(self.cancion.notas[i].nota)
                self.tocar(("demo", i), tecla, 0.8, ahora, del_usuario=False)
            self.pulso_vis = self.demo.pulso(ahora)
        elif self.modo == "guia":
            notas = self.cancion.notas
            meta = self.cancion.pulsos_totales if self.guia.terminada else notas[self.guia.indice].inicio
            self.pulso_vis += (meta - self.pulso_vis) * min(1.0, dt * 12.0)

    def tecla_pc(self, k: int, ahora: float) -> bool:
        """Atiende una tecla del PC. Devuelve ``False`` cuando hay que salir."""
        c = chr(k).lower() if 0 < k < 256 else ""
        if k == _ESC or c == "q":
            return False
        if c in ("1", "2", "3"):
            self.cambiar_modo(MODOS[int(c) - 1], ahora)
        elif c == "s":
            ids = list(CANCIONES)
            self.cancion_id = ids[(ids.index(self.cancion_id) + 1) % len(ids)]
            self.cambiar_modo(self.modo, ahora)
            self.avisar(self.cancion.nombre, ahora)
        elif c == "t":
            self.avisar("Timbre: " + config.NOMBRES_TIMBRE[self.audio.siguiente_timbre()], ahora)
        elif c == "r":
            self.cambiar_modo(self.modo, ahora)
        elif c in ("+", "="):
            # Umbral más bajo = hace falta doblar menos el dedo.
            self.avisar("Sensibilidad: umbral %d %%" % round(self.detector.ajustar(-0.02) * 100), ahora)
        elif c in ("-", "_"):
            self.avisar("Sensibilidad: umbral %d %%" % round(self.detector.ajustar(0.02) * 100), ahora)
        elif c == "h":
            self.ver_ayuda = not self.ver_ayuda
        elif c == "e":
            self.ver_esqueleto = not self.ver_esqueleto
        elif c == "f":
            self.pantalla_completa = not self.pantalla_completa
            self._aplicar_pantalla()
        elif c and c in config.TECLAS_PC:
            # El teclado del PC no avisa al soltar: la nota dura un tiempo fijo.
            voz = ("pc", c)
            self.notas_pc = [(v, fin) for v, fin in self.notas_pc if v != voz]
            self.tocar(voz, config.TECLAS_PC.index(c), 0.85, ahora)
            self.notas_pc.append((voz, ahora + 0.45))
        return True

    # ----------------------------------------------------------------- dibujo
    def componer(self, ahora: float) -> np.ndarray:
        """Dibuja la escena completa y devuelve el lienzo."""
        dt = 0.0 if self._t_dibujo is None else min(ahora - self._t_dibujo, 0.1)
        self._t_dibujo = ahora
        ui, guia, cancion = self.interfaz, self.guia, self.cancion
        con_pista = self.modo in ("guia", "demo")

        objetivo = None
        if self.modo == "guia" and not guia.terminada:
            objetivo = self.teclado.indice(guia.objetivo)
        if self.modo == "demo":
            sonando = [i for i, _ in self.demo.sonando]
            desde = min(sonando) if sonando else self.demo.indice
            actual = max(self.demo.indice - 1, 0)
            progreso = self.demo.pulso(ahora) / cancion.pulsos_totales
        else:
            desde = actual = guia.indice
            progreso = guia.indice / float(len(cancion))

        lienzo = ui.fondo(self._imagen)
        ui.nieve(lienzo, dt)
        ui.carriles(lienzo, objetivo)
        if con_pista:
            ui.pista(lienzo, cancion, self.pulso_vis, desde)
        ui.dibujar_teclado(lienzo, self.pulsadas.values(), objetivo, self.fallos, ahora,
                           con_teclas_pc=not self._camara_activa())
        ui.chispas(lienzo, dt)
        ui.manos(lienzo, self._manos, self.detector.lecturas, self.ver_esqueleto)

        fps = self.vision.fps if self.vision is not None else 0.0
        detalle = "%s  ·  %s" % (cancion.nombre, config.NOMBRES_TIMBRE[self.audio.timbre])
        if fps:
            detalle += "  ·  %d fps" % round(fps)
        ui.barra(lienzo, self.modo, detalle, progreso if con_pista else None)

        aviso, hasta = self._aviso
        if ahora < hasta:
            ui.aviso(lienzo, aviso, 130 if con_pista else 74)
        if con_pista:
            ui.letra(lienzo, cancion, actual)
        if self.modo == "guia":
            ui.marcador(lienzo, guia)
            if guia.terminada:
                ui.panel_final(lienzo, guia, ahora)
        estado = self._estado_camara(ahora)
        if estado:
            ui.aviso(lienzo, estado, 330)
        elif self.modo == "libre" and ahora >= hasta:
            ui.aviso(lienzo, "Modo libre: lleva el dedo al carril de una tecla y dóblalo para tocarla",
                     74, 19)
        if self.ver_ayuda:
            ui.ayuda(lienzo)
        return lienzo

    def _camara_activa(self) -> bool:
        return self.vision is not None and not self.vision.error

    def _estado_camara(self, ahora: float) -> str:
        if self.vision is None:
            return ""
        if self.vision.error:
            return "Sin cámara (%s). Toca con las teclas Z X C V B N M , . /" % self.vision.error
        if not self.vision.lista:
            return "Abriendo la cámara…"
        if self.modo != "demo" and ahora - self._t_manos > 2.0:
            return "Muestra tus manos a la cámara"
        return ""

    def _aplicar_pantalla(self) -> None:
        modo = cv2.WINDOW_FULLSCREEN if self.pantalla_completa else cv2.WINDOW_NORMAL
        cv2.setWindowProperty(config.TITULO, cv2.WND_PROP_FULLSCREEN, modo)

    # ------------------------------------------------------------------ bucle
    def ejecutar(self) -> int:
        cv2.namedWindow(config.TITULO, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(config.TITULO, config.ANCHO, config.ALTO)
        self._aplicar_pantalla()
        if self.vision is not None:
            self.vision.start()
        self._t_manos = anterior = time.perf_counter()
        try:
            while True:
                if self._camara_activa():
                    cuadro = self.vision.esperar(0.03)
                    if cuadro is not None:
                        self._imagen = cuadro.imagen
                        self.procesar_manos(cuadro.manos, cuadro.t)
                elif self._manos:
                    self.procesar_manos((), time.perf_counter())
                ahora = time.perf_counter()
                self.avanzar(ahora, ahora - anterior)
                anterior = ahora
                cv2.imshow(config.TITULO, self.componer(ahora))
                k = cv2.waitKey(1 if self._camara_activa() else 15)
                if k != -1 and not self.tecla_pc(k & 0xFF, ahora):
                    break
                if cv2.getWindowProperty(config.TITULO, cv2.WND_PROP_VISIBLE) < 1:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            if self.vision is not None:
                self.vision.detener()
            self.audio.cerrar()
            cv2.destroyAllWindows()
        return 0


def crear_argumentos() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="piano_aereo",
        description="Toca Jingle Bells en el aire: la cámara detecta tus dedos como en un piano.",
    )
    p.add_argument("--modo", choices=MODOS, default="guia", help="modo inicial (por defecto: guia)")
    p.add_argument("--cancion", choices=list(CANCIONES), default="coro", help="coro o canción completa")
    p.add_argument("--timbre", choices=config.TIMBRES, default="piano")
    p.add_argument("--camara", type=int, default=0, help="índice de la cámara (0 = la del portátil)")
    p.add_argument("--sensibilidad", type=float, default=config.SENSIBILIDAD,
                   help="cuánto hay que doblar el dedo, de 0.10 (poco) a 0.40 (mucho)")
    p.add_argument("--sin-camara", action="store_true", help="tocar solo con el teclado del PC")
    p.add_argument("--sin-espejo", action="store_true", help="no voltear la imagen como un espejo")
    p.add_argument("--sin-sonido", action="store_true")
    p.add_argument("--pantalla-completa", action="store_true")
    p.add_argument("--detalle", action="store_true", help="mostrar mensajes de diagnóstico")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = crear_argumentos().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.detalle else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    args.sensibilidad = min(max(args.sensibilidad, config.SENSIBILIDAD_MIN), config.SENSIBILIDAD_MAX)
    return App(args).ejecutar()
