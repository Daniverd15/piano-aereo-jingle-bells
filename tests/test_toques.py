import numpy as np

from piano_aereo import config
from piano_aereo.simulacion import mano_sintetica
from piano_aereo.toques import DetectorToques, extensiones

DT = 1 / 30.0
ABIERTA = (0, 0, 0, 0, 0)


def simular(detector, guion, t=0.0):
    """Reproduce una lista de (flexión por dedo, número de fotogramas)."""
    eventos = []
    for flexion, cuadros in guion:
        for _ in range(cuadros):
            t += DT
            eventos += detector.actualizar([mano_sintetica(400, 500, flexion=flexion)], t)
    return eventos, t


def test_extension_no_depende_de_la_distancia():
    cerca = extensiones(mano_sintetica(300, 400, tam=200))
    lejos = extensiones(mano_sintetica(300, 400, tam=60))
    assert np.allclose(cerca, lejos)


def test_doblar_un_dedo_toca_y_estirarlo_suelta():
    eventos, _ = simular(DetectorToques(), [(ABIERTA, 20), ((0, 1, 0, 0, 0), 6), (ABIERTA, 10)])
    assert [(e.pulsa, e.dedo) for e in eventos] == [(True, 1), (False, 1)]
    assert 0.5 <= eventos[0].fuerza <= 1.0


def test_cada_dedo_incluido_el_pulgar_puede_tocar():
    for dedo in range(5):
        flexion = [0.0] * 5
        flexion[dedo] = 1.0
        eventos, _ = simular(DetectorToques(), [(ABIERTA, 20), (flexion, 6), (ABIERTA, 10)])
        assert [(e.pulsa, e.dedo) for e in eventos] == [(True, dedo), (False, dedo)]


def test_la_tecla_se_elige_donde_estaba_la_punta_antes_de_doblar():
    punta = mano_sintetica(400, 500)[8]
    eventos, _ = simular(DetectorToques(), [(ABIERTA, 20), ((0, 1, 0, 0, 0), 6)])
    assert abs(eventos[0].x - punta[0]) < 2 and abs(eventos[0].y - punta[1]) < 2


def test_un_dedo_arrastrado_por_su_vecino_no_suena():
    eventos, _ = simular(DetectorToques(), [(ABIERTA, 20), ((0, 0, 0, 1.0, 0.45), 8)])
    assert [e.dedo for e in eventos if e.pulsa] == [3]


def test_dos_dedos_a_la_vez_forman_un_acorde():
    eventos, _ = simular(DetectorToques(), [(ABIERTA, 20), ((0, 1, 0, 1, 0), 6)])
    assert sorted(e.dedo for e in eventos if e.pulsa) == [1, 3]


def test_un_cambio_lento_de_postura_no_suena():
    guion = [((0, f, 0, 0, 0), 12) for f in np.linspace(0, 0.3, 30)]
    eventos, _ = simular(DetectorToques(), [(ABIERTA, 20)] + guion)
    assert eventos == []


def test_cerrar_la_mano_entera_no_suena():
    eventos, _ = simular(DetectorToques(), [(ABIERTA, 20), ((0, 1, 1, 1, 1), 6)])
    assert eventos == []


def test_una_mano_recien_aparecida_no_toca():
    eventos, _ = simular(DetectorToques(), [(ABIERTA, 2), ((0, 1, 0, 0, 0), 3)])
    assert eventos == []


def test_si_la_mano_desaparece_se_sueltan_sus_notas():
    d = DetectorToques()
    eventos, t = simular(d, [(ABIERTA, 20), ((0, 0, 1, 0, 0), 6)])
    assert eventos[-1].pulsa
    assert d.actualizar([], t + DT) == []  # un fotograma perdido se tolera
    sueltas = d.actualizar([], t + config.GRACIA + 0.1)
    assert [(e.pulsa, e.dedo) for e in sueltas] == [(False, 2)]


def test_dos_manos_reciben_nombres_estables():
    d = DetectorToques()
    t = 0.0
    izquierda = mano_sintetica(300, 500, derecha=False)
    for _ in range(20):
        t += DT
        d.actualizar([mano_sintetica(900, 500), izquierda], t)
    eventos = []
    for _ in range(6):
        t += DT
        eventos += d.actualizar([mano_sintetica(900, 500, flexion=(0, 1, 0, 0, 0)), izquierda], t)
    assert [(e.lado, e.dedo) for e in eventos] == [("der", 1)]
    # Si la izquierda sale de cuadro, la derecha conserva su nombre.
    for _ in range(15):
        t += DT
        d.actualizar([mano_sintetica(900, 500, flexion=(0, 1, 0, 0, 0))], t)
    assert {lectura.lado for lectura in d.lecturas} == {"der"}


def test_sensibilidad_acotada():
    d = DetectorToques()
    for _ in range(50):
        d.ajustar(-0.02)
    assert d.umbral == config.SENSIBILIDAD_MIN
    for _ in range(50):
        d.ajustar(0.02)
    assert d.umbral == config.SENSIBILIDAD_MAX
