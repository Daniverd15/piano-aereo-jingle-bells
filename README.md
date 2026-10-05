# Piano Aéreo — Jingle Bells con los dedos

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![MediaPipe](https://img.shields.io/badge/MediaPipe-Hand%20Landmarker-0097A7)
![OpenCV](https://img.shields.io/badge/OpenCV-visi%C3%B3n%20por%20computador-5C3EE8?logo=opencv&logoColor=white)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)

Aplicación de escritorio, escrita íntegramente en **Python**, que convierte la
cámara del portátil en un piano. Un teclado aparece en pantalla, la cámara
sigue las manos en tiempo real y, al doblar un dedo sobre una tecla, suena su
nota. Incluye un modo guiado para interpretar **Jingle Bells** nota a nota.

**Autor:** Daniel Enrique Villamizar Ramírez
**Asignatura:** Ciencia de Datos

![Interfaz en modo Guía](docs/captura.png)

<sub>Captura generada con manos simuladas mediante `scripts/generar_captura.py`. En uso real, el fondo es la imagen de la cámara.</sub>

---

## Contenido

1. [Objetivo](#objetivo)
2. [Características](#características)
3. [Requisitos](#requisitos)
4. [Instalación y ejecución](#instalación-y-ejecución)
5. [Cómo se toca](#cómo-se-toca)
6. [Modos y controles](#modos-y-controles)
7. [Cómo funciona](#cómo-funciona)
8. [Estructura del proyecto](#estructura-del-proyecto)
9. [Pruebas](#pruebas)
10. [Solución de problemas](#solución-de-problemas)
11. [Limitaciones](#limitaciones)
12. [Créditos y licencia](#créditos-y-licencia)

---

## Objetivo

Desarrollar una aplicación para portátil que permita tocar la canción *Jingle
Bells* con los dedos, detectándolos con la cámara como si se tratara de un
piano, usando únicamente Python.

## Características

- **Teclado de piano en pantalla.** Diez teclas blancas (Sol3 a Si4). Cualquier
  dedo de cualquiera de las dos manos puede tocar cualquier tecla, mantener
  notas y formar acordes.
- **Detección de toques sin calibración.** El sistema aprende solo cómo es cada
  dedo estirado y se adapta a la distancia y a la postura de la mano.
- **Tres modos de uso:** Libre, Guía (la canción espera a que se acierte cada
  nota) y Demo (la canción suena sola).
- **Jingle Bells en dos versiones:** el coro (51 notas) o la canción completa
  con estrofa (98 notas), con la letra en pantalla estilo karaoke.
- **Sonido sintetizado.** No se usan archivos de audio: cada nota se genera
  matemáticamente con NumPy. Tres timbres: piano, campanas y caja de música.
- **Respuesta en tiempo real.** Seguimiento de manos a 30 fotogramas por
  segundo y salida de audio de baja latencia.
- **Ayudas visuales.** Cada punta de dedo muestra una línea hacia la tecla que
  tocaría y un arco que indica cuánto falta para que suene.
- **Pruebas automáticas** que verifican el recorrido completo sin necesidad de
  cámara ni altavoces.

## Requisitos

| Requisito | Detalle |
|-----------|---------|
| Python | 3.9 o superior |
| Hardware | Portátil o PC con cámara web y salida de audio |
| Sistema operativo | Windows, macOS o Linux (desarrollado y probado en Windows 11) |

Dependencias (se instalan desde `requirements.txt`):

| Biblioteca | Uso en el proyecto |
|------------|--------------------|
| [MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) | Localiza 21 puntos de cada mano en la imagen |
| OpenCV | Captura de la cámara y dibujo de la interfaz (se instala junto con MediaPipe) |
| NumPy | Cálculos geométricos y síntesis de sonido |
| sounddevice | Salida de audio en tiempo real |
| Pillow | Texto con tildes y eñes en la interfaz |

## Instalación y ejecución

```bash
git clone https://github.com/Daniverd15/piano-aereo-jingle-bells.git
cd piano-aereo-jingle-bells
```

**Windows (opción rápida).** Hacer doble clic en `ejecutar.bat`. La primera vez
crea el entorno virtual e instala las dependencias; después abre la aplicación.

**Instalación manual (cualquier sistema).**

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m piano_aereo
```

El modelo de detección de manos está incluido en `modelos/`. Si faltara, la
aplicación lo descarga automáticamente al arrancar.

### Opciones de línea de comandos

| Opción | Descripción | Valor por defecto |
|--------|-------------|-------------------|
| `--modo {libre,guia,demo}` | Modo inicial | `guia` |
| `--cancion {coro,completa}` | Versión de Jingle Bells | `coro` |
| `--timbre {piano,campanas,cajita}` | Sonido del instrumento | `piano` |
| `--camara N` | Índice de la cámara | `0` |
| `--sensibilidad X` | Cuánto hay que doblar el dedo, de `0.10` (poco) a `0.40` (mucho) | `0.20` |
| `--sin-camara` | Tocar solo con el teclado del PC | desactivado |
| `--sin-espejo` | No voltear la imagen como un espejo | desactivado |
| `--sin-sonido` | Ejecutar sin audio | desactivado |
| `--pantalla-completa` | Abrir a pantalla completa | desactivado |
| `--detalle` | Mostrar mensajes de diagnóstico en la consola | desactivado |

Ejemplo:

```bash
python -m piano_aereo --modo demo --cancion completa --timbre campanas
```

## Cómo se toca

1. Colocar la mano frente a la cámara, a unos 40–60 cm, con la palma hacia ella
   y los dedos estirados.
2. Mover la mano hacia los lados. De cada punta de dedo sale una línea que cae
   sobre la tecla que ese dedo tocaría (su *carril*).
3. **Doblar el dedo**, como al pulsar una tecla: la nota suena. Al estirarlo de
   nuevo, la nota se apaga.

Para empezar es más fácil usar solo el dedo índice e ir moviendo la mano de
tecla en tecla. Con algo de práctica, se pueden dejar los cinco dedos sobre
Do–Sol y tocar el coro completo sin desplazar la mano.

## Modos y controles

| Tecla | Modo | Descripción |
|:-----:|------|-------------|
| `1` | **Libre** | Piano sin restricciones. |
| `2` | **Guía** | La tecla que corresponde se ilumina y la canción espera hasta que se toca la nota correcta. Registra aciertos, errores y racha, y al terminar muestra la precisión, el tiempo y de una a tres estrellas. |
| `3` | **Demo** | La canción suena sola, a tempo, con las notas cayendo sobre el teclado. Sirve para aprenderla; se puede tocar encima. |

| Tecla | Acción |
|-------|--------|
| `S` | Cambiar entre el coro y la canción completa |
| `T` | Cambiar el timbre |
| `+` / `-` | Aumentar / reducir la sensibilidad |
| `R` | Reiniciar la canción |
| `E` | Mostrar u ocultar el esqueleto de la mano |
| `F` | Pantalla completa |
| `H` | Ayuda en pantalla |
| `Z X C V B N M , . /` | Tocar las diez teclas con el teclado del PC |
| `Q` / `Esc` | Salir |

## Cómo funciona

```
 Cámara ──▶ MediaPipe ──▶ Detector de toques ──▶ Teclado ──▶ Sintetizador ──▶ Altavoces
 (hilo      21 puntos     ¿se acortó            tecla según    ondas generadas
  propio)   por mano      algún dedo?           la posición    con NumPy
                                                de la punta
```

### 1. Visión por computador — `vision.py`

Un hilo independiente captura la cámara, voltea la imagen como un espejo y
procesa cada fotograma con el modelo *Hand Landmarker* de MediaPipe, que
devuelve 21 puntos por mano (muñeca, nudillos, articulaciones y puntas). Al
ejecutarse separado del dibujo, la interfaz nunca se bloquea y siempre se
trabaja con el fotograma más reciente.

### 2. Detección de toques — `toques.py`

Es el núcleo del proyecto. La idea es que pulsar una tecla equivale a
**acortar un dedo** visto desde la cámara. Para cada dedo se calcula:

```
extensión = distancia(punta, nudillo) / tamaño de la palma
```

Al dividir por el tamaño de la palma, la medida es la misma con la mano cerca o
lejos de la cámara. Sobre esa señal se aplican varias reglas:

| Mecanismo | Problema que resuelve |
|-----------|-----------------------|
| **Referencia adaptativa** | Cada dedo guarda su extensión "en reposo", que sube rápido y baja despacio. Un toque (brusco) destaca; un cambio lento de postura se absorbe. No hace falta calibrar. |
| **Histéresis** | La nota se activa cuando el dedo se acorta un 20 % y solo se suelta al recuperar la mitad, lo que evita parpadeos en el umbral. |
| **Filtro de dominancia** | Al doblar un dedo, los vecinos se mueven un poco. Un dedo solo suena si su caída es comparable a la del que más ha bajado. |
| **Detección de cambio de postura** | Si cuatro o más dedos se acortan a la vez, la mano se está cerrando o inclinando: no se interpreta como toque. |
| **Antirrebote y calentamiento** | Tiempo mínimo entre dos cambios del mismo dedo, y una mano recién aparecida no puede tocar hasta estabilizarse. |
| **Dinámica** | La velocidad con que baja el dedo determina el volumen de la nota. |
| **Elección de tecla** | Se usa la posición de la punta *antes* de doblarse, porque al doblar el dedo la punta se desplaza. |

Las manos se identifican por su posición en pantalla y no por la lateralidad
que estima el modelo, que es poco fiable con la imagen en espejo.

### 3. Síntesis de sonido — `sintetizador.py`

Cada nota se calcula a partir de su frecuencia (`f = 440 · 2^((n − 69) / 12)`,
con `n` el número MIDI) mediante **síntesis aditiva**: se suman ondas
sinusoidales con distinta amplitud y velocidad de extinción.

- **Piano:** nueve armónicos ligeramente desafinados hacia arriba, como en una
  cuerda real, donde los agudos se apagan antes que los graves.
- **Campanas:** parciales no armónicos característicos de una campana afinada.
- **Caja de música:** pocos parciales de extinción rápida.

Las notas se mezclan en la función de retrollamada de `sounddevice`. El
mezclador es polifónico (una voz por dedo), aplica paneo estéreo según la
tecla, apaga la nota con suavidad al soltarla y usa un limitador `tanh` para
que los acordes no saturen.

### 4. Canción — `canciones.py`

La partitura se escribe como texto, una frase por línea, con el formato
`nota:pulsos:sílaba`:

```python
"E4:1:Jin- E4:1:gle E4:2:bells,"
```

Está en Do mayor. Las diez teclas del teclado, de Sol3 a Si4, cubren
exactamente el rango que necesitan la estrofa y el coro.

### 5. Interfaz — `interfaz.py` y `texto.py`

Toda la escena se dibuja con OpenCV sobre la imagen de la cámara: carriles,
notas que caen, teclado, manos, letra y paneles. Como OpenCV solo dibuja
caracteres ASCII, los textos se rasterizan con Pillow y se guardan en caché.

## Estructura del proyecto

```
piano-aereo-jingle-bells/
├── piano_aereo/
│   ├── app.py            Bucle principal, modos y teclas
│   ├── vision.py         Cámara y MediaPipe en un hilo propio
│   ├── toques.py         De los puntos de la mano a toques de piano
│   ├── notas.py          Notas, frecuencias y geometría del teclado
│   ├── sintetizador.py   Síntesis de notas y mezclador en tiempo real
│   ├── canciones.py      Partitura de Jingle Bells; modos Guía y Demo
│   ├── interfaz.py       Dibujo de la escena
│   ├── texto.py          Texto con tildes sobre OpenCV
│   ├── simulacion.py     Mano sintética para pruebas
│   └── config.py         Constantes ajustables
├── modelos/              Modelo de manos de MediaPipe
├── tests/                Pruebas automáticas (pytest)
├── scripts/              Generador de la captura de pantalla
├── docs/                 Imágenes de la documentación
├── ejecutar.bat          Instalación y arranque en Windows
├── main.py               Atajo: python main.py
└── requirements.txt
```

## Pruebas

```bash
python -m pip install pytest
python -m pytest
```

El proyecto incluye 26 pruebas que no requieren cámara ni altavoces. Una mano
sintética (`simulacion.py`) dobla los dedos y se comprueba, entre otras cosas:

- que cada uno de los cinco dedos puede pulsar y soltar una tecla;
- que un cambio lento de postura, cerrar la mano o un dedo arrastrado por su
  vecino **no** producen notas;
- que las notas se sueltan si la mano sale de la imagen;
- que la partitura cabe en el teclado y cuadra en compases de 4/4;
- que las ondas sintetizadas tienen la frecuencia correcta y no producen
  chasquidos;
- de extremo a extremo, que se puede tocar el coro completo en modo Guía sin
  errores.

## Solución de problemas

| Síntoma | Qué hacer |
|---------|-----------|
| Suenan notas sin querer | Pulsar `-` para reducir la sensibilidad. Mantener la mano quieta al tocar. |
| Cuesta que suenen las notas | Pulsar `+`. Doblar el dedo con un movimiento rápido y marcado. |
| No detecta las manos | Mejorar la iluminación frontal, evitar contraluz y acercar la mano a 40–60 cm. |
| Se abre otra cámara | Probar con `--camara 1` (o `2`). |
| Aparece "Sin cámara" | Cerrar otras aplicaciones que la estén usando (Zoom, Teams, etc.). Mientras tanto se puede tocar con el teclado del PC. |
| No hay sonido | Revisar el dispositivo de salida del sistema. Con `--detalle` se ve qué dispositivo de audio se abrió. |

## Limitaciones

- El teclado solo tiene teclas blancas (escala de Do mayor), suficientes para
  Jingle Bells pero no para canciones con sostenidos o bemoles.
- La detección depende de la iluminación y de que la mano se vea completa.
- Los toques se detectan mejor con la palma hacia la cámara; con la mano de
  perfil la longitud aparente de los dedos cambia menos.
- Desarrollado y probado en Windows 11 con Python 3.13. El código mantiene
  sintaxis compatible con Python 3.9, pero no se ha ejecutado en esa versión.

## Créditos y licencia

- Detección de manos: [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker), de Google, bajo licencia Apache 2.0.
- *Jingle Bells*: James Lord Pierpont, 1857 (dominio público).

© 2026 Daniel Enrique Villamizar Ramírez. Código publicado bajo la [licencia MIT](LICENSE).
