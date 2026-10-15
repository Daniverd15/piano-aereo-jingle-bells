# Registro de cambios

## [1.4.0] — 2026-10-14

### Añadido
- Datos de cada interpretación en CSV (`grabaciones/datos_*.csv`) al terminar
  una canción en Guía o Ritmo, y `scripts/analizar_sesion.py` para analizarlos
  (puntería temporal, aciertos por dedo y evolución entre sesiones).
- Gráfico de puntería en los resultados del modo Ritmo y **calibración
  automática del retraso** de la cámara con `L` (mediana de los desfases).
- Espectro de frecuencias en vivo con `O` (FFT con ventana de Hann e
  interpolación del pico) y nombre de la nota dominante.
- Árbol de Navidad que se adorna con los aciertos, estrella, fuegos
  artificiales y fanfarria de campanas al terminar.
- Gesto de puño en la pantalla de resultados para repetir la canción.
- Ajustes recordados entre sesiones (`ajustes.json`, `--ajustes-de-fabrica`).
- La nieve se aparta de las puntas de los dedos.
- 16 pruebas nuevas (67 en total); las pruebas escriben solo en carpetas temporales.

## [1.3.0] — 2026-10-14

### Añadido
- Segunda forma de tocar, **cinco dedos** (tecla `5` o `--cinco-dedos`): cada
  dedo recibe automáticamente una tecla según dónde está la mano, como en la
  técnica de cinco dedos del piano. El coro de Jingle Bells se toca sin mover
  la mano.
- Números de digitación (1 pulgar … 5 meñique) sobre las teclas asignadas, y
  el dedo que debe tocar la siguiente nota resaltado en Guía y Ritmo.
- Aviso en Guía cuando la nota que toca queda fuera de las cinco teclas.
- 6 pruebas nuevas (51 en total).

## [1.2.0] — 2026-10-14

### Añadido
- Evaluación cuantitativa del detector (`scripts/evaluar_detector.py`): sesiones
  sintéticas etiquetadas, precisión, sensibilidad, F1, latencia, barridos de
  umbral, ruido y suavizado, escenario de toques suaves y estudio de ablación.
  Genera `docs/evaluacion.png` y `docs/RESULTADOS_EVALUACION.md`.
- Informe técnico (`docs/INFORME.md`).
- Grabación de vídeo (`.mp4`) y audio (`.wav`) de la interpretación con `G`, y
  captura de pantalla con `I`, en la carpeta `grabaciones/`.
- Registro de la sesión en `piano_aereo.log`.
- Prueba de regresión de calidad del detector y pruebas de robustez (45 en total).

### Cambiado
- Detector: **rechazo de modo común**. Las notas fantasma al cerrar o relajar
  la mano bajan de 13,0 a 1,3 por minuto en la evaluación.
- Umbral 0,20 → 0,22 y suavizado 0,6 → 0,8, elegidos con la evaluación (F1
  0,948 → 0,961 y 10 ms menos de latencia).
- `ejecutar.bat` encuentra Python también con el lanzador `py` y permite pasar
  opciones (`ejecutar.bat --modo ritmo`).

### Robustez
- La cámara se reconecta sola si no abre, se desconecta o deja de enviar
  imagen, y prueba DirectShow y Media Foundation.
- La salida de audio se reabre sola si se pierde (por ejemplo, al desconectar
  unos audífonos).
- Un error inesperado al dibujar, al procesar las manos o al atender una tecla
  ya no cierra la aplicación: se salta ese fotograma y queda en el registro.
- Un error dentro del mezclador de audio produce silencio en ese bloque en vez
  de detener el sonido para siempre.
- Silenciados los avisos internos de MediaPipe en la consola.

## [1.1.0] — 2026-10-13

### Añadido
- Modo **Ritmo** al estilo *Guitar Hero*: notas a tempo, calificación
  Perfecto / Bien / Fallo, combo con multiplicador hasta x4, puntuación y
  calificación final de D a S.
- Acompañamiento sintetizado (bajo, acordes, cascabeles) con cuenta atrás.
- Tres dificultades (84, 108 y 132 pulsos por minuto).
- Asistencia de puntería para toques al borde de la tecla esperada.
- Aviso de cámara con imagen negra y opción `--diagnostico`.

### Cambiado
- La Demo suena con acompañamiento y precisión de muestra; pasa a la tecla `4`.

## [1.0.0] — 2026-10-04

### Añadido
- Piano de diez teclas en pantalla tocado con los dedos frente a la cámara,
  con MediaPipe Hand Landmarker.
- Detector de toques sin calibración (referencia adaptativa, histéresis,
  filtro de dominancia).
- Sintetizador propio con NumPy (piano, campanas, caja de música) y mezclador
  polifónico de baja latencia con `sounddevice`.
- *Jingle Bells* (coro y canción completa) con letra; modos Libre, Guía y Demo.
- Pruebas automáticas con una mano sintética.
