"""Bucle principal: une visión, detección de toques, audio, canción e interfaz."""

from __future__ import annotations

import argparse
import logging
import math
import time
from typing import Dict, Hashable, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import config
from .asignacion import CincoDedos
from .canciones import CANCIONES, Demo, Guia, Ritmo
from .grabacion import Grabadora, guardar_captura
from .interfaz import Interfaz
from .notas import Teclado, solfeo
from .sintetizador import MotorAudio, acompanamiento
from .toques import DetectorToques, Toque

log = logging.getLogger(__name__)

MODOS = ("libre", "guia", "ritmo", "demo")
_ESC = 27
_FONDO = "fondo"  # voz del motor de audio reservada al acompañamiento


class App:
    def __init__(self, args: argparse.Namespace) -> None:
        self.teclado = Teclado(
            config.NOTAS_TECLADO, config.TECLADO_MARGEN, config.TECLADO_Y,
            config.ANCHO - 2 * config.TECLADO_MARGEN, config.TECLADO_ALTO,
        )
        self.interfaz = Interfaz(self.teclado)
        self.detector = DetectorToques(args.sensibilidad)
        self.audio = MotorAudio(self.teclado.notas, args.timbre, activo=not args.sin_sonido)
        self.vision = None
        if not args.sin_camara:
            from .vision import Vision

            self.vision = Vision(args.camara, espejo=not args.sin_espejo)
        self.pantalla_completa = args.pantalla_completa

        self.cancion_id = args.cancion
        self.dificultad = args.dificultad
        self.asistencia = not args.sin_asistencia
        # Forma de tocar: apuntar el dedo a una tecla, o cinco dedos (cada dedo, una tecla).
        self.cinco_dedos = args.cinco_dedos
        self.cinco = CincoDedos(self.teclado)
        self.acompanar = not args.sin_acompanamiento
        self.modo = "libre"
        self.pulso_vis = 0.0
        self.pulsadas: Dict[Hashable, int] = {}  # voz -> tecla que mantiene pulsada
        self.fallos: Dict[int, float] = {}  # tecla -> instante del último error
        self.notas_pc: List[Tuple[Hashable, float]] = []  # (voz, instante de soltar)
        self.ver_ayuda = False
        self.ver_esqueleto = True
        self._ondas: Dict[Hashable, np.ndarray] = {}  # acompañamientos ya renderizados
        self._aviso: Tuple[str, float] = ("", 0.0)
        self._imagen: Optional[np.ndarray] = None
        self._manos: Sequence[np.ndarray] = ()
        self._t_manos = 0.0
        self._t_dibujo: Optional[float] = None
        self.grabadora = Grabadora()
        self._lienzo: Optional[np.ndarray] = None  # última pantalla dibujada
        self._errores = 0
        self.cambiar_modo(args.modo, time.perf_counter())

    # ----------------------------------------------------------------- estado
    @property
    def cancion(self):
        return CANCIONES[self.cancion_id]

    def avisar(self, cadena: str, ahora: float, segundos: float = 2.0) -> None:
        self._aviso = (cadena, ahora + segundos)

    def _onda_fondo(self, bpm: float, melodia: Optional[str]) -> np.ndarray:
        clave = (self.cancion_id, bpm, melodia, self.acompanar, self.audio.fm)
        if clave not in self._ondas:
            self._ondas[clave] = acompanamiento(
                self.cancion, bpm, self.audio.fm, Ritmo.ENTRADA, melodia, self.acompanar)
        return self._ondas[clave]

    def cambiar_modo(self, modo: str, ahora: float) -> None:
        """Entra en un modo (o lo reinicia) con la canción desde el principio."""
        self.modo = modo
        self.audio.silenciar()
        self.pulsadas.clear()
        self.fallos.clear()
        self.notas_pc = []
        self.interfaz.limpiar_efectos()
        _, bpm, ventanas = config.DIFICULTADES[self.dificultad]
        con_fondo = modo in ("ritmo", "demo")
        if con_fondo:
            # En Demo la melodía va dentro de la misma onda que el
            # acompañamiento, así suena exactamente a tempo.
            inicio = time.perf_counter()
            onda = self._onda_fondo(bpm, self.audio.timbre if modo == "demo" else None)
            ahora += time.perf_counter() - inicio  # lo que tardó en renderizarse
            self.audio.tocar_onda(_FONDO, onda, config.VOLUMEN_FONDO)
        # La pantalla se retrasa lo que tarda el sonido en salir por los
        # altavoces, para que la nota cruce la línea justo cuando se oye el pulso.
        t0 = ahora + self.audio.latencia
        self.guia = Guia(self.cancion)
        self.ritmo = Ritmo(self.cancion, bpm, ventanas, t0)
        self.demo = Demo(self.cancion, t0, bpm)
        self.pulso_vis = -Ritmo.ENTRADA if con_fondo else 0.0

    def _objetivos(self, t: float) -> Iterable[int]:
        """Teclas que la canción espera en este momento (para la asistencia)."""
        if self.modo == "guia" and not self.guia.terminada:
            return [self.teclado.indice(self.guia.objetivo)]
        if self.modo == "ritmo":
            notas = self.cancion.notas
            return [self.teclado.indice(notas[i].nota) for i in self.ritmo.candidatas(t)]
        return ()

    def tecla_para(self, toque: Toque, t: float) -> Optional[int]:
        """Tecla que toca un dedo: la asignada (cinco dedos) o la de su carril (apuntar)."""
        if self.cinco_dedos:
            return self.cinco.tecla(toque.lado, toque.dedo)
        x = toque.x
        tecla = self.teclado.tecla_en(x)
        if self.asistencia:
            objetivos = list(self._objetivos(t))
            if tecla not in objetivos:
                iman = config.IMAN * self.teclado.ancho_tecla
                cercanas = [o for o in objetivos if self.teclado.distancia(o, x) <= iman]
                if cercanas:
                    return min(cercanas, key=lambda o: self.teclado.distancia(o, x))
        return tecla

    def tocar(self, voz: Hashable, tecla: int, fuerza: float, ahora: float,
              t_juicio: Optional[float] = None) -> None:
        """Hace sonar una tecla tocada por el usuario y la pasa al modo de juego."""
        nota = self.teclado.notas[tecla]
        self.audio.tocar(voz, nota, fuerza, self.teclado.paneo(tecla))
        self.pulsadas[voz] = tecla
        chispas = 12
        if self.modo == "guia":
            if self.guia.pulsar(nota, ahora) is False:
                self.fallos[tecla] = ahora
        elif self.modo == "ritmo":
            acierto = self.ritmo.pulsar(nota, ahora if t_juicio is None else t_juicio)
            chispas = 6
            if acierto is not None:
                self.interfaz.cartel(tecla, acierto[1], ahora)
                chispas = 32 if acierto[1] == "perfecto" else 18
        self.interfaz.chispear(tecla, chispas)

    def soltar(self, voz: Hashable) -> None:
        self.audio.soltar(voz)
        self.pulsadas.pop(voz, None)

    # ----------------------------------------------------------------- lógica
    def procesar_manos(self, manos: Sequence[np.ndarray], t: float) -> None:
        """Pasa las manos de un fotograma por el detector y hace sonar los toques."""
        self._manos = manos
        if manos:
            self._t_manos = t
        eventos = self.detector.actualizar(manos, t)
        # Se recalcula siempre, para que cambiar de forma de tocar sea instantáneo;
        # con un dedo pulsado, la posición de esa mano queda fija.
        self.cinco.actualizar(self.detector.lecturas)
        for toque in eventos:
            if not toque.pulsa:
                self.soltar(toque.voz)
                continue
            # El dedo se movió un poco antes de que llegara el fotograma.
            t_real = t - config.RETRASO_CAMARA
            tecla = self.tecla_para(toque, t_real)
            if tecla is not None:
                self.tocar(toque.voz, tecla, toque.fuerza, t, t_real)

    def avanzar(self, ahora: float, dt: float) -> None:
        """Lógica que depende del tiempo y no de la cámara."""
        for voz, t_fin in list(self.notas_pc):
            if ahora >= t_fin:
                self.soltar(voz)
                self.notas_pc.remove((voz, t_fin))
        notas = self.cancion.notas
        if self.modo == "demo":
            empiezan, terminan = self.demo.actualizar(ahora)
            for i in terminan:
                self.pulsadas.pop(("demo", i), None)
            for i in empiezan:  # el sonido ya va en la onda de fondo: solo se dibuja
                tecla = self.teclado.indice(notas[i].nota)
                self.pulsadas[("demo", i)] = tecla
                self.interfaz.chispear(tecla)
            self.pulso_vis = self.demo.pulso(ahora)
            if self.demo.terminada(ahora):
                self.cambiar_modo("demo", ahora)
        elif self.modo == "ritmo":
            for i in self.ritmo.actualizar(ahora):
                tecla = self.teclado.indice(notas[i].nota)
                self.fallos[tecla] = ahora
                self.interfaz.cartel(tecla, "fallo", ahora)
            self.pulso_vis = self.ritmo.pulso(ahora)
        elif self.modo == "guia":
            meta = self.cancion.pulsos_totales if self.guia.terminada else notas[self.guia.indice].inicio
            self.pulso_vis += (meta - self.pulso_vis) * min(1.0, dt * 12.0)

    def tecla_pc(self, k: int, ahora: float) -> bool:
        """Atiende una tecla del PC. Devuelve ``False`` cuando hay que salir."""
        c = chr(k).lower() if 0 < k < 256 else ""
        if k == _ESC or c == "q":
            return False
        if c in ("1", "2", "3", "4"):
            self.cambiar_modo(MODOS[int(c) - 1], ahora)
        elif c == "s":
            ids = list(CANCIONES)
            self.cancion_id = ids[(ids.index(self.cancion_id) + 1) % len(ids)]
            self.cambiar_modo(self.modo, ahora)
            self.avisar(self.cancion.nombre, ahora)
        elif c == "d":
            ids = list(config.DIFICULTADES)
            self.dificultad = ids[(ids.index(self.dificultad) + 1) % len(ids)]
            self.cambiar_modo(self.modo, ahora)
            nombre, bpm, _ = config.DIFICULTADES[self.dificultad]
            self.avisar("Dificultad: %s (%d pulsos por minuto)" % (nombre, bpm), ahora)
        elif c == "t":
            nombre = config.NOMBRES_TIMBRE[self.audio.siguiente_timbre()]
            if self.modo == "demo":  # la melodía de la demo va en la onda de fondo
                self.cambiar_modo(self.modo, ahora)
            self.avisar("Timbre: " + nombre, ahora)
        elif c == "p":
            self.acompanar = not self.acompanar
            if self.modo in ("ritmo", "demo"):
                self.cambiar_modo(self.modo, ahora)
            self.avisar("Acompañamiento: " + ("sí" if self.acompanar else "no"), ahora)
        elif c == "5":
            self.cinco_dedos = not self.cinco_dedos
            self.avisar("Forma de tocar: " + ("cinco dedos (cada dedo, una tecla)" if self.cinco_dedos
                                              else "apuntar con el dedo a la tecla"), ahora, 3.0)
        elif c == "a":
            self.asistencia = not self.asistencia
            self.avisar("Asistencia: " + ("activada" if self.asistencia else "desactivada"), ahora)
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
        elif c == "g":
            self.alternar_grabacion(ahora)
        elif c == "i" and self._lienzo is not None:
            try:
                ruta = guardar_captura(self._lienzo, self.grabadora.carpeta)
                self.avisar("Captura guardada en grabaciones/%s" % ruta.name, ahora, 3.0)
            except OSError as exc:
                self.avisar("No se pudo guardar la captura: %s" % exc, ahora, 3.0)
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
        dt = 0.0 if self._t_dibujo is None else min(max(ahora - self._t_dibujo, 0.0), 0.1)
        self._t_dibujo = ahora
        ui, guia, ritmo, cancion = self.interfaz, self.guia, self.ritmo, self.cancion
        notas = cancion.notas
        con_pista = self.modo != "libre"

        objetivo, estados = None, None
        if self.modo == "demo":
            sonando = [i for i, _ in self.demo.sonando]
            desde = min(sonando) if sonando else self.demo.indice
            actual = max(self.demo.indice - 1, 0)
            progreso = self.pulso_vis / cancion.pulsos_totales
        elif self.modo == "ritmo":
            estados = ritmo.estados
            desde = max(ritmo.primera - 6, 0)
            actual = next((i for i in range(desde, len(notas))
                           if notas[i].inicio + notas[i].pulsos > self.pulso_vis), len(notas))
            progreso = self.pulso_vis / cancion.pulsos_totales
        else:
            if self.modo == "guia" and not guia.terminada:
                objetivo = self.teclado.indice(guia.objetivo)
            desde = actual = guia.indice
            progreso = guia.indice / float(len(cancion))

        lienzo = ui.fondo(self._imagen)
        ui.nieve(lienzo, dt)
        ui.carriles(lienzo, objetivo, autopista=con_pista)
        if con_pista:
            ui.pista(lienzo, cancion, self.pulso_vis, desde, estados)
        asignadas = self.cinco.teclas() if self.cinco_dedos else None
        ui.dibujar_teclado(lienzo, self.pulsadas.values(), objetivo, self.fallos, ahora,
                           con_teclas_pc=not self._camara_activa(), asignadas=asignadas)
        ui.chispas(lienzo, dt)
        ui.carteles(lienzo, ahora)
        siguiente = self._siguiente_tecla()
        resaltar = self.cinco.dedo_para(siguiente) if asignadas and siguiente is not None else None
        ui.manos(lienzo, self._manos, self.detector.lecturas, self.ver_esqueleto, asignadas, resaltar, ahora)

        detalle = cancion.nombre
        if self.modo in ("ritmo", "demo"):
            detalle += "  ·  " + config.DIFICULTADES[self.dificultad][0]
        detalle += "  ·  " + config.NOMBRES_TIMBRE[self.audio.timbre]
        detalle += "  ·  " + ("5 dedos" if self.cinco_dedos else "Apuntar")
        if self.vision is not None and self.vision.fps:
            detalle += "  ·  %d fps" % round(self.vision.fps)
        ui.barra(lienzo, self.modo, detalle, progreso if con_pista else None)

        aviso, hasta = self._aviso
        if ahora < hasta:
            ui.aviso(lienzo, aviso, 130 if con_pista else 74)
        if con_pista:
            ui.letra(lienzo, cancion, actual)
        en_cuenta_atras = self.modo in ("ritmo", "demo") and self.pulso_vis < 0
        if en_cuenta_atras:
            ui.aviso(lienzo, str(max(1, int(math.ceil(-self.pulso_vis)))), 230, 120)
        if self.modo == "guia":
            ui.marcador(lienzo, guia)
            if guia.terminada:
                ui.panel_final(lienzo, guia, ahora)
        elif self.modo == "ritmo":
            ui.marcador_ritmo(lienzo, ritmo)
            if ritmo.terminada(ahora):
                ui.panel_final_ritmo(lienzo, ritmo)
        estado = self._estado_camara(ahora)
        if estado and not en_cuenta_atras:
            ui.aviso(lienzo, estado, 330)
        elif self.modo == "libre" and ahora >= hasta:
            ui.aviso(lienzo, "Modo libre: coloca la mano sobre el teclado; cada dedo toca una tecla (5 para apuntar)"
                     if self.cinco_dedos else
                     "Modo libre: lleva el dedo al carril de una tecla y dóblalo para tocarla (5 para cinco dedos)",
                     74, 19)
        elif (self.modo == "guia" and asignadas and siguiente is not None and resaltar is None
              and ahora >= hasta and not guia.terminada):
            # La nota que toca no cae bajo ninguna mano: hay que desplazarla.
            ui.aviso(lienzo, "Mueve la mano hasta que %s quede bajo un dedo" % solfeo(self.teclado.notas[siguiente]),
                     130, 19)
        if self.ver_ayuda:
            ui.ayuda(lienzo)
        return lienzo

    def alternar_grabacion(self, ahora: float) -> None:
        """Empieza o termina de grabar vídeo y audio en ``grabaciones/``."""
        try:
            if self.grabadora.activa:
                rutas = self.grabadora.detener()
                self.avisar("Guardado en grabaciones/: " + " + ".join(r.name for r in rutas), ahora, 4.0)
            else:
                self.grabadora.iniciar(self.audio, ahora)
                self.avisar("Grabando vídeo y audio (G para terminar)", ahora)
        except OSError as exc:
            log.exception("Fallo en la grabación")
            self.avisar("No se pudo grabar: %s" % exc, ahora, 3.0)

    def _siguiente_tecla(self) -> Optional[int]:
        """Tecla de la próxima nota que hay que tocar (Guía y Ritmo)."""
        notas = self.cancion.notas
        if self.modo == "guia" and not self.guia.terminada:
            return self.teclado.indice(self.guia.objetivo)
        if self.modo == "ritmo":
            for i in range(self.ritmo.primera, len(notas)):
                if self.ritmo.estados[i] is None:
                    return self.teclado.indice(notas[i].nota)
        return None

    def _camara_activa(self) -> bool:
        return self.vision is not None and not self.vision.error

    def _estado_camara(self, ahora: float) -> str:
        if self.vision is None:
            return ""
        if self.vision.error:
            return "Sin cámara (%s), reintentando… Mientras, toca con Z X C V B N M , . /" % self.vision.error
        if not self.vision.lista:
            return "Abriendo la cámara…"
        if self.vision.oscura:
            return "La cámara da imagen negra: abre su tapa o cierra otras apps que la usen"
        en_resultados = self.modo == "ritmo" and self.ritmo.terminada(ahora)
        if self.modo != "demo" and not en_resultados and ahora - self._t_manos > 2.0:
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
        # La canción empieza al abrirse la ventana, no al crear la aplicación.
        self.cambiar_modo(self.modo, anterior)
        try:
            while True:
                ahora = self._paso(anterior)
                anterior = ahora
                k = cv2.waitKey(1 if self._camara_activa() else 15)
                if k != -1 and not self._proteger(self.tecla_pc, k & 0xFF, ahora):
                    break
                if cv2.getWindowProperty(config.TITULO, cv2.WND_PROP_VISIBLE) < 1:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            if self.grabadora.activa:
                self.grabadora.detener()
            if self.vision is not None:
                self.vision.detener()
            self.audio.cerrar()
            cv2.destroyAllWindows()
        return 0

    def _paso(self, anterior: float) -> float:
        """Un fotograma completo: cámara, lógica, dibujo y grabación."""
        if self._camara_activa():
            cuadro = self.vision.esperar(0.03)
            if cuadro is not None:
                self._imagen = cuadro.imagen
                self._proteger(self.procesar_manos, cuadro.manos, cuadro.t)
        else:
            self._imagen = None
            if self._manos:  # la cámara se perdió con dedos pulsados: soltarlos
                self._proteger(self.procesar_manos, (), time.perf_counter())
        ahora = time.perf_counter()
        if self.audio.vigilar(ahora):
            self._ondas.clear()  # estaban renderizadas para la frecuencia anterior
            self._proteger(self.cambiar_modo, self.modo, ahora)
        self._proteger(self.avanzar, ahora, ahora - anterior)
        lienzo = self._proteger(self.componer, ahora)
        if lienzo is None:  # si falla el dibujo se repite la última pantalla
            lienzo = self._lienzo if self._lienzo is not None else self.interfaz.fondo(None)
        self._lienzo = lienzo
        self._proteger(self.grabadora.cuadro, lienzo, ahora)
        if self.grabadora.activa:
            lienzo = lienzo.copy()
            self.interfaz.indicador_grabacion(lienzo, self.grabadora.duracion(ahora), ahora)
        cv2.imshow(config.TITULO, lienzo)
        return ahora

    def _proteger(self, funcion, *args):
        """Ejecuta ``funcion`` sin dejar que un error inesperado cierre la aplicación.

        En una presentación es preferible saltarse un fotograma a que la
        ventana se cierre. El error queda en ``piano_aereo.log``.
        """
        try:
            return funcion(*args)
        except Exception:
            self._errores += 1
            if self._errores <= 5 or self._errores % 100 == 0:
                log.exception("Error inesperado en %s (n.º %d)", funcion.__name__, self._errores)
            return True if funcion == self.tecla_pc else None


def diagnostico(camara: int) -> int:
    """Comprueba modelo, cámara, seguimiento de manos y audio sin abrir el piano."""
    from .vision import Vision, asegurar_modelo

    fallos = 0

    def informe(nombre: str, ok: bool, texto: str) -> None:
        nonlocal fallos
        fallos += 0 if ok else 1
        print("[%s] %-10s %s" % ("OK" if ok else "FALLO", nombre, texto))

    try:
        ruta = asegurar_modelo()
        informe("Modelo", True, "%s (%.1f MB)" % (ruta.name, ruta.stat().st_size / 1e6))
    except Exception as exc:
        informe("Modelo", False, str(exc))
    vision = Vision(camara)
    vision.start()
    # Hasta 10 s para que la cámara arranque y luego 3 s midiendo.
    cuadros, forma, inicio, primero = 0, None, time.perf_counter(), None
    while not vision.error:
        ahora = time.perf_counter()
        if (primero is None and ahora - inicio > 10.0) or (primero is not None and ahora - primero > 3.0):
            break
        cuadro = vision.esperar(0.1)
        if cuadro is not None:
            primero = cuadro.t if primero is None else primero
            cuadros, forma = cuadros + 1, cuadro.imagen.shape
    fps = (cuadros - 1) / 3.0
    vision.detener()
    if vision.error or not cuadros:
        informe("Cámara", False, vision.error or "no llegó ninguna imagen de la cámara %d" % camara)
    elif vision.oscura:
        informe("Cámara", False, "la cámara %d da imagen negra: abre su tapa de privacidad o "
                                 "cierra otras aplicaciones que la estén usando" % camara)
    else:
        informe("Cámara", fps >= 15, "cámara %d, %dx%d, seguimiento de manos a %d fps%s" % (
            camara, forma[1], forma[0], round(fps),
            "" if fps >= 15 else " (muy lento: mejora la luz o cierra otros programas)"))
    audio = MotorAudio(config.NOTAS_TECLADO)
    informe("Audio", audio.disponible, "%d Hz, latencia %d ms" % (audio.fm, round(audio.latencia * 1000))
            if audio.disponible else "no se pudo abrir la salida de sonido")
    audio.cerrar()
    print("Todo listo para tocar." if not fallos else "Hay %d problema(s) que revisar." % fallos)
    return 1 if fallos else 0


def crear_argumentos() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="piano_aereo",
        description="Toca Jingle Bells en el aire: la cámara detecta tus dedos como en un piano.",
    )
    p.add_argument("--modo", choices=MODOS, default="guia", help="modo inicial (por defecto: guia)")
    p.add_argument("--cancion", choices=list(CANCIONES), default="coro", help="coro o canción completa")
    p.add_argument("--dificultad", choices=list(config.DIFICULTADES), default="normal",
                   help="velocidad de los modos Ritmo y Demo")
    p.add_argument("--timbre", choices=config.TIMBRES, default="piano")
    p.add_argument("--camara", type=int, default=0, help="índice de la cámara (0 = la del portátil)")
    p.add_argument("--sensibilidad", type=float, default=config.SENSIBILIDAD,
                   help="cuánto hay que doblar el dedo, de 0.10 (poco) a 0.40 (mucho)")
    p.add_argument("--sin-asistencia", action="store_true",
                   help="no perdonar los toques que caen al borde de la tecla esperada")
    p.add_argument("--cinco-dedos", action="store_true",
                   help="cada dedo toca una tecla según dónde esté la mano, sin apuntar")
    p.add_argument("--sin-acompanamiento", action="store_true",
                   help="modos Ritmo y Demo sin bajo, acordes ni cascabeles")
    p.add_argument("--sin-camara", action="store_true", help="tocar solo con el teclado del PC")
    p.add_argument("--sin-espejo", action="store_true", help="no voltear la imagen como un espejo")
    p.add_argument("--sin-sonido", action="store_true")
    p.add_argument("--pantalla-completa", action="store_true")
    p.add_argument("--diagnostico", action="store_true",
                   help="comprobar cámara, modelo y audio, y salir")
    p.add_argument("--detalle", action="store_true", help="mostrar mensajes de diagnóstico")
    return p


def configurar_registro(detalle: bool) -> None:
    """Consola con avisos (o todo con ``--detalle``) y archivo ``piano_aereo.log`` completo."""
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    consola = logging.StreamHandler()
    consola.setLevel(logging.INFO if detalle else logging.WARNING)
    consola.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    raiz.addHandler(consola)
    try:
        archivo = logging.FileHandler(str(config.RAIZ / "piano_aereo.log"), mode="w", encoding="utf-8")
    except OSError:
        return
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz.addHandler(archivo)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = crear_argumentos().parse_args(argv)
    configurar_registro(args.detalle)
    if args.diagnostico:
        return diagnostico(args.camara)
    args.sensibilidad = min(max(args.sensibilidad, config.SENSIBILIDAD_MIN), config.SENSIBILIDAD_MAX)
    return App(args).ejecutar()
