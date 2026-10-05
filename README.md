# Piano Aéreo — Jingle Bells con los dedos

Aplicación de escritorio en **Python puro** que convierte la cámara del portátil
en un piano: un teclado aparece en pantalla, la cámara sigue tus dedos y, al
doblar un dedo sobre una tecla, suena su nota. Incluye un modo guiado para tocar
**Jingle Bells** nota a nota.

![Interfaz en modo Guía](docs/captura.png)

*Captura generada con manos simuladas (`scripts/generar_captura.py`); en uso real el fondo es la imagen de la cámara.*

## Cómo se toca

1. Pon la mano frente a la cámara, con los dedos estirados.
2. Muévela a los lados: cada punta de dedo tiene una línea que cae hasta la
   tecla que tocaría (su *carril*).
3. **Dobla el dedo** como si pulsaras la tecla y la nota suena. Estíralo para soltarla.

Funciona como un piano de verdad: cualquier dedo de cualquier mano toca
cualquier tecla, se pueden mantener notas y hacer acordes. Si colocas una mano
con los cinco dedos sobre Do–Sol, el coro de Jingle Bells sale sin mover la mano.

## Instalación

Requiere **Python 3.9 o superior** y un portátil con cámara.

En Windows basta con hacer doble clic en **`ejecutar.bat`**: la primera vez crea
el entorno e instala todo, y luego abre el piano.

A mano (Windows, macOS o Linux):

```bash
python -m venv .venv
.venv\Scripts\activate          # en macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m piano_aereo
```

El modelo de detección de manos ya viene en `modelos/`; si faltara, se descarga
solo al arrancar.

## Modos

| Tecla | Modo | Qué hace |
|:-----:|------|----------|
| `1` | **Libre** | Piano sin más: toca lo que quieras. |
| `2` | **Guía** | Jingle Bells paso a paso. La tecla que toca se ilumina y la canción **espera** a que aciertes; lleva la cuenta de aciertos, errores y racha, y al final te pone de una a tres estrellas. |
| `3` | **Demo** | La canción suena sola, a tempo, con las notas cayendo sobre el teclado y la letra en karaoke. Sirve para aprendérsela (y puedes tocar encima). |

## Controles

| Tecla | Acción |
|-------|--------|
| `S` | Cambiar canción: coro (51 notas) o canción completa con estrofa (98 notas) |
| `T` | Cambiar timbre: piano, campanas, caja de música |
| `+` / `-` | Más / menos sensibilidad (cuánto hay que doblar el dedo) |
| `R` | Reiniciar la canción |
| `E` | Mostrar u ocultar el esqueleto de la mano |
| `F` | Pantalla completa |
| `H` | Ayuda en pantalla |
| `Z X C V B N M , . /` | Tocar las diez teclas con el teclado del PC |
| `Q` / `Esc` | Salir |

Opciones al arrancar (`python -m piano_aereo --help`):

```bash
python -m piano_aereo --modo demo --cancion completa --timbre campanas
python -m piano_aereo --camara 1          # otra cámara
python -m piano_aereo --sin-camara        # solo teclado del PC
```

## Cómo funciona

```
cámara ──> MediaPipe ──> detector de toques ──> tecla (carril) ──> sintetizador ──> altavoces
 (hilo)    21 puntos      ¿se acortó un dedo?     según la x de       ondas hechas
           por mano                               la punta            con NumPy
```

**1. Visión** (`vision.py`). Un hilo aparte captura la cámara, pone la imagen en
espejo y pasa cada fotograma por el *Hand Landmarker* de MediaPipe, que devuelve
21 puntos por mano. Al ir en su propio hilo, la interfaz nunca se congela.

**2. Detección de toques** (`toques.py`). Es el corazón del proyecto. Para cada
dedo se calcula su **longitud aparente** (distancia punta–nudillo) dividida por
el tamaño de la palma, de modo que la medida es la misma con la mano cerca o
lejos. Doblar el dedo lo acorta, y eso es lo que se detecta:

- **Referencia adaptativa.** Cada dedo guarda su longitud "estirado", que sube
  rápido y baja despacio. Así no hace falta calibrar: un toque (brusco) destaca,
  y un cambio lento de postura se absorbe sin sonar.
- **Histéresis.** La nota entra cuando el dedo se acorta un 20 % y solo se
  suelta al recuperar la mitad, para que no tiemble en el umbral.
- **Dedos arrastrados.** Al doblar el anular, el meñique se mueve un poco con
  él. Un dedo solo suena si su caída es comparable a la del que más ha bajado.
- **Mano que se cierra o se inclina.** Si casi todos los dedos se acortan a la
  vez no es un toque: se toma como la nueva postura de reposo.
- **Fuerza.** Cuanto más rápido baja el dedo, más fuerte suena la nota.
- **Tecla.** Se elige con la posición que tenía la punta *antes* de doblarse,
  porque al doblar el dedo la punta se desplaza.

**3. Sonido** (`sintetizador.py`). No hay archivos de audio. Cada nota se genera
con síntesis aditiva en NumPy (el piano suma nueve armónicos ligeramente
desafinados, como una cuerda real, que se apagan a ritmos distintos) y se mezcla
en el *callback* de `sounddevice`. Es polifónico, con paneo estéreo según la
tecla y un limitador suave para que los acordes no saturen.

**4. Canción** (`canciones.py`). Jingle Bells está escrita como texto
(`nota:pulsos:sílaba`), en Do mayor. Las diez teclas blancas, de Sol3 a Si4, son
justo el rango que necesitan estrofa y coro.

**5. Interfaz** (`interfaz.py`, `texto.py`). Todo se dibuja con OpenCV sobre la
imagen de la cámara. Los textos se rasterizan con Pillow para tener tildes y eñes.

## Estructura

```
piano_aereo/
  app.py           bucle principal y teclas
  vision.py        cámara + MediaPipe en un hilo
  toques.py        de puntos de la mano a toques de piano
  notas.py         notas, frecuencias y geometría del teclado
  sintetizador.py  síntesis de las notas y mezclador en tiempo real
  canciones.py     partitura de Jingle Bells, modos Guía y Demo
  interfaz.py      dibujo de la escena
  texto.py         texto con tildes sobre OpenCV
  simulacion.py    mano sintética para pruebas
modelos/           modelo de manos de MediaPipe
tests/             pruebas automáticas (pytest)
scripts/           generador de la captura de pantalla
```

## Pruebas

```bash
python -m pip install pytest
python -m pytest
```

Las pruebas no necesitan cámara ni altavoces: una mano sintética dobla los dedos
y se comprueba todo el recorrido, hasta tocar el coro entero en modo Guía sin
errores.

## Consejos

- Buena luz de frente y un fondo sin mucho movimiento ayudan a la detección.
- Coloca la mano a unos 40–60 cm de la cámara, con la palma hacia ella.
- Si suenan notas sin querer, pulsa `-`; si te cuesta que suenen, pulsa `+`.
- Para empezar, toca solo con el dedo índice moviendo la mano de tecla en tecla.

## Créditos

- Detección de manos: [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) (Google, Apache 2.0).
- *Jingle Bells*: James Lord Pierpont, 1857 (dominio público).
- Código bajo licencia MIT.
