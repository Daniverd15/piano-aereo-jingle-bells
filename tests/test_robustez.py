"""La aplicación no debe caerse: cámara que falla, audio que se pierde, errores al dibujar."""

import time
import wave

import cv2
import numpy as np

from piano_aereo import config, vision
from piano_aereo.app import App, crear_argumentos
from piano_aereo.grabacion import Grabadora, guardar_captura
from piano_aereo.sintetizador import MotorAudio


def crear(*extra):
    return App(crear_argumentos().parse_args(["--sin-camara", "--sin-sonido"] + list(extra)))


# ------------------------------------------------------------------- cámara
class _RastreadorFalso:
    def detectar(self, bgr, t, ancho, alto):
        return []

    def cerrar(self):
        pass


class _CamaraFalsa:
    """Simula una cámara: no abre con ningún controlador, luego da 5 imágenes y se
    'desconecta', y al reabrirla funciona."""

    aperturas = 0

    def __init__(self, indice, api=None):
        _CamaraFalsa.aperturas += 1
        self.intento = _CamaraFalsa.aperturas
        self.leidas = 0

    def isOpened(self):
        return self.intento > 2  # fallan los dos controladores del primer intento

    def set(self, *args):
        return True

    def getBackendName(self):
        return "FALSO"

    def read(self):
        self.leidas += 1
        if self.intento == 3 and self.leidas > 5:
            return False, None
        time.sleep(0.002)
        return True, np.full((480, 640, 3), 120, np.uint8)

    def release(self):
        pass


def test_la_camara_se_reconecta_sola(monkeypatch):
    _CamaraFalsa.aperturas = 0
    monkeypatch.setattr(vision, "Rastreador", _RastreadorFalso)
    monkeypatch.setattr(vision.cv2, "VideoCapture", _CamaraFalsa)
    monkeypatch.setattr(vision.Vision, "REINTENTO", 0.05)
    monkeypatch.setattr(vision.Vision, "FALLOS_SEGUIDOS", 3)
    v = vision.Vision(0)
    v.start()
    errores_vistos = set()
    limite = time.perf_counter() + 5
    while time.perf_counter() < limite:
        if v.error:
            errores_vistos.add(v.error)
        if _CamaraFalsa.aperturas >= 4 and v.lista and v.error is None:
            break
        time.sleep(0.005)
    v.detener()
    assert any("no se pudo abrir" in e for e in errores_vistos)
    assert any("dejó de enviar" in e for e in errores_vistos)
    assert v.lista and v.error is None and not v.is_alive()
    assert v.esperar(0.1).imagen.shape == (360, 640, 3)  # 640x480 recortada a 16:9


def test_imagen_negra_se_detecta(monkeypatch):
    v = vision.Vision(0)
    v.lista, v.brillo = True, 3.0
    assert v.oscura
    v.brillo = 90.0
    assert not v.oscura


def test_sin_camara_se_sueltan_las_notas_y_se_avisa(monkeypatch):
    from piano_aereo.simulacion import mano_sintetica

    app = crear("--modo", "libre")
    t = 0.0
    for flexion, n in (((0, 0, 0, 0, 0), 15), ((0, 1, 0, 0, 0), 5)):
        for _ in range(n):
            t += 1 / 30
            app.procesar_manos([mano_sintetica(500, 480, flexion=flexion)], t)
    assert app.pulsadas

    class VisionCaida:
        error, lista, fps, oscura = "la cámara dejó de enviar imagen", False, 0.0, False

    app.vision = VisionCaida()
    monkeypatch.setattr(cv2, "imshow", lambda *a: None)
    anterior = time.perf_counter()
    for _ in range(3):
        time.sleep(config.GRACIA / 2)
        anterior = app._paso(anterior)
    assert not app.pulsadas and app._imagen is None
    assert "reintentando" in app._estado_camara(anterior)


# -------------------------------------------------------------------- audio
def test_el_audio_se_reabre_si_se_pierde(monkeypatch):
    motor = MotorAudio(config.NOTAS_TECLADO, activo=False)
    motor._activo = True

    class FlujoMuerto:
        active = False

        def stop(self):
            pass

        def close(self):
            pass

    def abrir_a_48k():
        motor.fm, motor.disponible, motor._flujo = 48000, True, None

    motor._flujo = FlujoMuerto()
    monkeypatch.setattr(motor, "_abrir", abrir_a_48k)
    motor.tocar("a", "C4")
    assert motor.vigilar(10.0) is True
    assert motor.disponible and motor.fm == 48000 and not motor._voces
    # Las notas se vuelven a sintetizar a la nueva frecuencia: misma duración en segundos.
    assert len(motor._muestras[("piano", "C4")]) == int(48000 * config.DURACION_NOTA)
    assert motor.vigilar(11.0) is False  # solo revisa cada 3 s


def test_un_error_al_mezclar_da_silencio_y_no_corta_el_audio(monkeypatch):
    motor = MotorAudio(config.NOTAS_TECLADO, activo=False)
    monkeypatch.setattr(motor, "mezclar", lambda n: 1 / 0)
    salida = np.ones((256, 2), np.float32)
    motor._callback(salida, 256, None, None)
    assert not salida.any() and motor._fallos_callback == 1


# --------------------------------------------------------------- protección
def test_un_error_al_dibujar_no_cierra_la_aplicacion(monkeypatch):
    app = crear()
    monkeypatch.setattr(cv2, "imshow", lambda *a: None)
    anterior = app._paso(time.perf_counter())
    buena = app._lienzo.copy()
    monkeypatch.setattr(app, "componer", lambda ahora: 1 / 0)
    monkeypatch.setattr(app, "avanzar", lambda ahora, dt: [][1])
    for _ in range(3):
        anterior = app._paso(anterior)
    assert app._errores == 6 and np.array_equal(app._lienzo, buena)
    monkeypatch.setattr(app, "cambiar_modo", lambda *a: 1 / 0)
    assert app._proteger(app.tecla_pc, ord("2"), anterior) is True  # una tecla con error no cierra


# ---------------------------------------------------------------- grabación
def test_grabar_video_y_audio(tmp_path):
    motor = MotorAudio(config.NOTAS_TECLADO, activo=False)
    motor.disponible, motor.fm = True, 16000  # sin altavoz: se alimenta la mezcla a mano
    grabadora = Grabadora(tmp_path)
    video = grabadora.iniciar(motor, 0.0)
    assert grabadora.activa and motor.toma == []
    lienzo = np.zeros((config.ALTO, config.ANCHO, 3), np.uint8)
    motor.tocar("a", "A4", 1.0)
    for i in range(30):  # un segundo a 30 fps...
        motor.mezclar(16000 // 30)
        grabadora.cuadro(lienzo, i / 30.0)
    grabadora.cuadro(lienzo, 1.5)  # ...y un atasco de medio segundo
    rutas = grabadora.detener()
    assert rutas == [video, video.with_suffix(".wav")] and not grabadora.activa
    captura = cv2.VideoCapture(str(video))
    # Tras el atasco se rellena hasta tiempo real, pero como mucho medio segundo (15 cuadros).
    assert int(captura.get(cv2.CAP_PROP_FRAME_COUNT)) == 30 + 15
    captura.release()
    with wave.open(str(rutas[1])) as wav:
        assert (wav.getnchannels(), wav.getframerate()) == (2, 16000)
        assert wav.getnframes() == 30 * (16000 // 30)
        assert np.abs(np.frombuffer(wav.readframes(2000), "<i2")).max() > 1000  # se oye la nota
    assert motor.toma is None  # deja de acumular audio
    assert guardar_captura(lienzo, tmp_path).suffix == ".png"


def test_grabar_con_teclas_desde_la_aplicacion(tmp_path, monkeypatch):
    app = crear()
    app.grabadora = Grabadora(tmp_path)
    monkeypatch.setattr(cv2, "imshow", lambda *a: None)
    ahora = app._paso(time.perf_counter())
    app.tecla_pc(ord("g"), ahora)
    for _ in range(5):
        ahora = app._paso(ahora)
    app.tecla_pc(ord("i"), ahora)
    app.tecla_pc(ord("g"), ahora)
    nombres = sorted(p.suffix for p in tmp_path.iterdir())
    assert nombres == [".mp4", ".png"]  # sin sonido no hay .wav
    assert "Guardado" in app._aviso[0]
