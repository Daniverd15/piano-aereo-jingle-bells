"""Constantes de la aplicación. Todo lo ajustable vive aquí."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_MODELO = RAIZ / "modelos" / "hand_landmarker.task"
URL_MODELO = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

TITULO = "Piano Aereo - Jingle Bells"
ANCHO, ALTO = 1280, 720

# ---------------------------------------------------------------- teclado
# Diez teclas blancas: el rango exacto que necesita Jingle Bells completa
# (estrofa + coro) en Do mayor.
NOTAS_TECLADO = ("G3", "A3", "B3", "C4", "D4", "E4", "F4", "G4", "A4", "B4")
TECLADO_MARGEN = 40
TECLADO_Y = 548
TECLADO_ALTO = 164
# Fila inferior del teclado del PC: respaldo para tocar sin cámara.
TECLAS_PC = "zxcvbnm,./"

# ------------------------------------------------------- detección de toques
SENSIBILIDAD = 0.20  # caída relativa del dedo que dispara la nota
SENSIBILIDAD_MIN, SENSIBILIDAD_MAX = 0.10, 0.40
SOLTAR = 0.5  # la nota se suelta al volver por debajo de umbral * SOLTAR
SUAVIZADO = 0.6  # peso de la medida nueva en el filtro exponencial
TAU_REPOSO = 2.5  # s que tarda la referencia de "dedo estirado" en adaptarse
DOMINANCIA = 0.6  # un dedo arrastrado por su vecino no dispara
REBOTE = 0.07  # s mínimos entre dos cambios del mismo dedo
CALENTAMIENTO = 0.3  # s que debe verse una mano antes de poder tocar
GRACIA = 0.25  # s que se tolera perder la mano sin soltar las notas
RAPIDEZ_MAX = 3.0  # palmas/s: por encima la mano se está desplazando
SOSTENIDO_MAX = 5.0  # s máximos con un dedo pulsado

# ------------------------------------------------------------------ audio
FRECUENCIA_MUESTREO = 44_100
DURACION_NOTA = 3.0
VOLUMEN = 0.8
TIMBRES = ("piano", "campanas", "cajita")
NOMBRES_TIMBRE = {"piano": "Piano", "campanas": "Campanas", "cajita": "Caja de música"}

# ----------------------------------------------------------------- pista
PX_POR_PULSO = 70
PISTA_Y_MIN = 118

# ----------------------------------------------------------------- juego
# Dificultad: (nombre, pulsos por minuto, (tolerancia perfecto, tolerancia bien) en s).
DIFICULTADES = {
    "facil": ("Fácil", 84, (0.14, 0.28)),
    "normal": ("Normal", 108, (0.12, 0.24)),
    "dificil": ("Difícil", 132, (0.10, 0.20)),
}
# Retraso medio entre mover el dedo y que la cámara entregue el fotograma.
RETRASO_CAMARA = 0.05
# Asistencia: un toque que cae junto a la tecla esperada, a menos de esta
# fracción del ancho de tecla, cuenta como si hubiera caído en ella.
IMAN = 0.3
VOLUMEN_FONDO = 0.8
