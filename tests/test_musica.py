import numpy as np
import pytest

from piano_aereo import config
from piano_aereo.canciones import CANCIONES, Demo, Guia
from piano_aereo.notas import Teclado, a_midi, frecuencia, solfeo
from piano_aereo.sintetizador import MotorAudio, sintetizar


def teclado():
    return Teclado(config.NOTAS_TECLADO, 40, 548, 1200, 164)


def test_notas():
    assert a_midi("C4") == 60 and a_midi("A4") == 69 and a_midi("F#3") == 54 and a_midi("Bb4") == 70
    assert frecuencia("A4") == pytest.approx(440.0)
    assert frecuencia("C4") == pytest.approx(261.63, abs=0.01)
    assert solfeo("G3") == "Sol"
    with pytest.raises(ValueError):
        a_midi("H2")


def test_carriles_del_teclado():
    t = teclado()
    assert t.tecla_en(39) is None and t.tecla_en(1240) is None
    assert t.tecla_en(40) == 0 and t.tecla_en(1239.9) == 9
    for i in range(len(t)):
        assert t.tecla_en(t.centro(i)) == i
    assert t.paneo(0) < 0 < t.paneo(9)


@pytest.mark.parametrize("identificador", list(CANCIONES))
def test_la_cancion_cabe_en_el_teclado_y_cuadra_en_compases(identificador):
    cancion = CANCIONES[identificador]
    assert {n.nota for n in cancion.notas} <= set(config.NOTAS_TECLADO)
    for primero, fin in cancion.frases:  # compás de 4/4: cada frase son compases enteros
        assert sum(n.pulsos for n in cancion.notas[primero:fin]) % 4 == 0
    assert cancion.frases[0][0] == 0 and cancion.frases[-1][1] == len(cancion)
    assert cancion.frase_de(len(cancion) - 1) == cancion.frases[-1]


def test_el_coro_empieza_como_jingle_bells():
    coro = CANCIONES["coro"]
    assert [n.nota for n in coro.notas[:11]] == ["E4"] * 7 + ["G4", "C4", "D4", "E4"]
    assert coro.pulsos_totales == 64
    assert CANCIONES["completa"].pulsos_totales == 128


def test_guia_espera_la_nota_correcta():
    g = Guia(CANCIONES["coro"])
    assert g.objetivo == "E4"
    assert g.pulsar("C4", 1.0) is False
    assert (g.indice, g.errores, g.racha) == (0, 1, 0)
    assert g.pulsar("E4", 2.0) is True
    assert (g.indice, g.aciertos, g.racha) == (1, 1, 1)
    for n in g.cancion.notas[1:]:
        assert g.pulsar(n.nota, 3.0) is True
    total = len(g.cancion)
    assert g.terminada and g.objetivo is None and g.pulsar("E4", 4.0) is None
    assert g.precision == pytest.approx(total / (total + 1.0)) and g.estrellas == 3
    assert g.duracion(99.0) == pytest.approx(2.0)


def test_demo_toca_todas_las_notas_en_orden_y_las_suelta():
    cancion = CANCIONES["coro"]
    d = Demo(cancion, 0.0)
    empezadas, terminadas = [], []
    fin = (cancion.pulsos_totales + Demo.ENTRADA + 1) * 60 / cancion.bpm
    for t in np.arange(0, fin, 1 / 60.0):
        a, b = d.actualizar(float(t))
        empezadas += a
        terminadas += b
    assert empezadas == list(range(len(cancion)))
    assert sorted(terminadas) == empezadas
    assert d.pulso(Demo.ENTRADA * 60 / cancion.bpm) == pytest.approx(0.0)


@pytest.mark.parametrize("timbre", config.TIMBRES)
def test_sintesis(timbre):
    onda = sintetizar(440.0, timbre, 44100, 1.0)
    assert onda.dtype == np.float32 and len(onda) == 44100
    assert np.isfinite(onda).all() and np.abs(onda).max() == pytest.approx(0.9, abs=1e-3)
    assert abs(onda[0]) < 1e-3 and abs(onda[-1]) < 1e-3  # sin chasquidos
    # La frecuencia dominante es la nota pedida.
    espectro = np.abs(np.fft.rfft(onda))
    assert abs(np.argmax(espectro) - 440) <= 2


def test_mezclador():
    motor = MotorAudio(config.NOTAS_TECLADO, activo=False)
    assert not motor.disponible
    assert not motor.mezclar(256).any()
    motor.tocar("a", "C4", 1.0, paneo=-1.0)
    motor.tocar("b", "E4", 1.0, paneo=1.0)
    bloque = motor.mezclar(2048)
    assert bloque.shape == (2048, 2) and bloque.dtype == np.float32
    assert np.abs(bloque).max() <= 1.0 and bloque[:, 0].any() and bloque[:, 1].any()
    motor.soltar("a")
    motor.soltar("b")
    for _ in range(40):
        bloque = motor.mezclar(2048)
    assert np.abs(bloque).max() < 1e-3  # al soltar, la nota se apaga
    assert not motor._colas
    motor.tocar("a", "C4")
    motor.tocar("a", "D4")  # repetir en la misma voz no acumula voces
    assert len(motor._voces) == 1 and len(motor._colas) == 1
    assert motor.siguiente_timbre() == "campanas"


def test_ritmo_califica_segun_la_punteria():
    from piano_aereo.canciones import Ritmo

    r = Ritmo(CANCIONES["coro"], 120, (0.10, 0.20), t0=0.0)  # un pulso = 0.5 s
    assert r.instante(0) == pytest.approx(Ritmo.ENTRADA * 0.5)
    assert r.pulso(r.instante(0)) == pytest.approx(0.0)
    assert r.pulsar("E4", r.instante(0) - 0.5) is None  # demasiado pronto: no cuenta
    assert r.pulsar("C4", r.instante(0)) is None  # tecla equivocada
    assert r.pulsar("E4", r.instante(0) + 0.05) == (0, "perfecto")
    assert r.pulsar("E4", r.instante(1) - 0.15) == (1, "bien")
    assert (r.puntos, r.combo, r.aciertos) == (160, 2, 2)
    assert r.actualizar(r.instante(2) + 0.19) == []  # aún se puede tocar
    assert r.actualizar(r.instante(2) + 0.21) == [2]  # se pasó: fallo y adiós combo
    assert (r.combo, r.mejor_combo, r.conteo["fallo"]) == (0, 2, 1)
    assert r.pulsar("E4", r.instante(2) + 0.21) is None  # una nota fallada ya no puntúa


def test_ritmo_el_combo_multiplica_hasta_x4():
    from piano_aereo.canciones import Ritmo

    r = Ritmo(CANCIONES["coro"], 120, (0.10, 0.20), t0=0.0)
    for i, n in enumerate(r.cancion.notas):
        assert r.multiplicador == min(4, 1 + i // Ritmo.COMBO_POR_NIVEL)
        assert r.pulsar(n.nota, r.instante(i)) == (i, "perfecto")
        assert r.actualizar(r.instante(i)) == []
    assert r.precision == 1.0 and r.calificacion == "S" and r.estrellas == 5
    assert not r.terminada(r.instante(len(r.cancion) - 1)) and r.terminada(r.instante(0) + 60)


@pytest.mark.parametrize("identificador", list(CANCIONES))
def test_hay_un_acorde_por_compas(identificador):
    from piano_aereo.sintetizador import ACORDES

    cancion = CANCIONES[identificador]
    assert len(cancion.acordes) * 4 == cancion.pulsos_totales
    assert set(cancion.acordes) <= set(ACORDES)


def test_acompanamiento():
    from piano_aereo.sintetizador import acompanamiento

    cancion, fm, bpm = CANCIONES["coro"], 16000, 120
    fondo = acompanamiento(cancion, bpm, fm, entrada=4.0)
    assert fondo.dtype == np.float32 and np.isfinite(fondo).all()
    assert len(fondo) == int((4 + 64 + 3) * 0.5 * fm)
    assert 0.3 < np.abs(fondo).max() < 1.0  # se oye y no satura
    # La cuenta atrás son cuatro clics, uno por pulso, y entre ellos hay silencio.
    pulso = int(0.5 * fm)
    for k in range(4):
        assert np.abs(fondo[k * pulso:k * pulso + 200]).max() > 0.2
        assert np.abs(fondo[k * pulso + pulso // 2:(k + 1) * pulso - 10]).max() < 0.01
    solo_clics = acompanamiento(cancion, bpm, fm, fondo=False)
    assert not solo_clics[4 * pulso:].any()
    con_melodia = acompanamiento(cancion, bpm, fm, melodia="piano", fondo=False)
    # La primera nota (Mi4, 329.6 Hz) suena justo al acabar la cuenta atrás.
    trozo = con_melodia[4 * pulso:5 * pulso]
    espectro = np.abs(np.fft.rfft(trozo))
    assert abs(np.argmax(espectro) * fm / len(trozo) - 329.6) < 4
