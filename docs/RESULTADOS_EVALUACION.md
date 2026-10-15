# Resultados de la evaluación del detector

Generado por `scripts/evaluar_detector.py` (semilla 2026): 6 sesiones sintéticas de 60 s a 30 fps con 295 toques reales, más arrastres del dedo vecino, cambios lentos de postura, inclinaciones de la muñeca, cierres de la mano, desplazamientos entre teclas y cambios de distancia a la cámara. Ruido supuesto: 0.8 % del tamaño de la mano. Un toque cuenta como detectado si suena el dedo correcto en los 350 ms siguientes a que empiece a bajar.

![Evaluación](evaluacion.png)

## Según el umbral

| Umbral | Precisión | Sensibilidad | F1 | Latencia media | Falsos/min |
|---|---:|---:|---:|---:|---:|
| 0.08 | 0.769 | 0.881 | 0.821 | 48 ms | 13.0 |
| 0.10 | 0.792 | 0.905 | 0.845 | 54 ms | 11.7 |
| 0.12 | 0.815 | 0.912 | 0.861 | 61 ms | 10.2 |
| 0.14 | 0.839 | 0.915 | 0.875 | 66 ms | 8.7 |
| 0.16 | 0.884 | 0.932 | 0.908 | 71 ms | 6.0 |
| 0.18 | 0.925 | 0.956 | 0.940 | 77 ms | 3.8 |
| 0.20 | 0.943 | 0.953 | 0.948 | 84 ms | 2.8 |
| 0.22 (elegido) | 0.972 | 0.949 | 0.961 | 89 ms | 1.3 |
| 0.24 | 0.989 | 0.946 | 0.967 | 93 ms | 0.5 |
| 0.26 | 0.993 | 0.939 | 0.965 | 99 ms | 0.3 |
| 0.28 | 0.993 | 0.912 | 0.951 | 105 ms | 0.3 |
| 0.30 | 0.996 | 0.864 | 0.926 | 111 ms | 0.2 |
| 0.32 | 0.996 | 0.800 | 0.887 | 114 ms | 0.2 |
| 0.34 | 1.000 | 0.732 | 0.845 | 119 ms | 0.0 |
| 0.36 | 1.000 | 0.664 | 0.798 | 121 ms | 0.0 |
| 0.38 | 0.994 | 0.576 | 0.730 | 125 ms | 0.2 |
| 0.40 | 1.000 | 0.505 | 0.671 | 126 ms | 0.0 |

Mejor F1 en este barrido: umbral 0.24 (F1 = 0.967).

## Según el ruido de los puntos (umbral 0.22)

| Ruido | Precisión | Sensibilidad | F1 | Latencia media | Falsos/min |
|---|---:|---:|---:|---:|---:|
| 0.0 % | 0.986 | 0.956 | 0.971 | 87 ms | 0.7 |
| 0.4 % | 0.983 | 0.959 | 0.971 | 88 ms | 0.8 |
| 0.8 % | 0.972 | 0.949 | 0.961 | 89 ms | 1.3 |
| 1.2 % | 0.962 | 0.946 | 0.954 | 89 ms | 1.8 |
| 1.6 % | 0.956 | 0.949 | 0.952 | 91 ms | 2.2 |
| 2.0 % | 0.949 | 0.953 | 0.951 | 93 ms | 2.5 |
| 2.5 % | 0.943 | 0.956 | 0.949 | 96 ms | 2.8 |

## Elección de umbral y suavizado

Suavizado = peso de la medida nueva en el filtro exponencial (1.0 = sin suavizar). Valores actuales: suavizado 0.8, umbral 0.22.

| Suavizado · umbral · ruido | Precisión | Sensibilidad | F1 | Latencia media | Falsos/min |
|---|---:|---:|---:|---:|---:|
| 0.6 · 0.20 · 0.8 % | 0.946 | 0.949 | 0.948 | 95 ms | 2.7 |
| 0.6 · 0.20 · 2.5 % | 0.934 | 0.953 | 0.943 | 100 ms | 3.3 |
| 0.6 · 0.22 · 0.8 % | 0.979 | 0.953 | 0.966 | 99 ms | 1.0 |
| 0.6 · 0.22 · 2.5 % | 0.949 | 0.946 | 0.947 | 105 ms | 2.5 |
| 0.6 · 0.24 · 0.8 % | 0.989 | 0.942 | 0.965 | 105 ms | 0.5 |
| 0.6 · 0.24 · 2.5 % | 0.972 | 0.953 | 0.962 | 113 ms | 1.3 |
| 0.8 · 0.20 · 0.8 % | 0.943 | 0.953 | 0.948 | 84 ms | 2.8 |
| 0.8 · 0.20 · 2.5 % | 0.922 | 0.956 | 0.938 | 89 ms | 4.0 |
| 0.8 · 0.22 · 0.8 % | 0.972 | 0.949 | 0.961 | 89 ms | 1.3 |
| 0.8 · 0.22 · 2.5 % | 0.943 | 0.956 | 0.949 | 96 ms | 2.8 |
| 0.8 · 0.24 · 0.8 % | 0.989 | 0.946 | 0.967 | 93 ms | 0.5 |
| 0.8 · 0.24 · 2.5 % | 0.956 | 0.956 | 0.956 | 101 ms | 2.2 |
| 1.0 · 0.20 · 0.8 % | 0.940 | 0.959 | 0.950 | 76 ms | 3.0 |
| 1.0 · 0.20 · 2.5 % | 0.886 | 0.953 | 0.918 | 82 ms | 6.0 |
| 1.0 · 0.22 · 0.8 % | 0.972 | 0.953 | 0.962 | 82 ms | 1.3 |
| 1.0 · 0.22 · 2.5 % | 0.922 | 0.959 | 0.940 | 88 ms | 4.0 |
| 1.0 · 0.24 · 0.8 % | 0.989 | 0.953 | 0.971 | 86 ms | 0.5 |
| 1.0 · 0.24 · 2.5 % | 0.943 | 0.953 | 0.948 | 94 ms | 2.8 |

## Con toques más suaves

Las mismas sesiones, pero con toques que doblan el dedo entre un 35 % y un 70 % (en lugar de 55 %-100 %), como haría alguien que toca con timidez.

| Umbral | Precisión | Sensibilidad | F1 | Latencia media | Falsos/min |
|---|---:|---:|---:|---:|---:|
| 0.18 | 0.930 | 0.895 | 0.912 | 102 ms | 3.3 |
| 0.20 | 0.946 | 0.834 | 0.886 | 108 ms | 2.3 |
| 0.22 (elegido) | 0.969 | 0.732 | 0.834 | 114 ms | 1.2 |
| 0.24 | 0.995 | 0.671 | 0.802 | 118 ms | 0.2 |
| 0.26 | 0.994 | 0.576 | 0.730 | 124 ms | 0.2 |

## Ablación (umbral 0.22, ruido 0.8 %)

| Variante | Precisión | Sensibilidad | F1 | Latencia media | Falsos/min |
|---|---:|---:|---:|---:|---:|
| Detector completo | 0.972 | 0.949 | 0.961 | 89 ms | 1.3 |
| Sin rechazo de modo común | 0.785 | 0.966 | 0.866 | 75 ms | 13.0 |
| Sin filtro de dominancia | 0.962 | 0.949 | 0.956 | 89 ms | 1.8 |
| Sin referencia adaptativa | 0.909 | 0.919 | 0.914 | 88 ms | 4.5 |
| Sin regla de cambio de postura | 0.972 | 0.949 | 0.961 | 89 ms | 1.3 |
| Sin bloqueo al desplazar la mano | 0.969 | 0.949 | 0.959 | 89 ms | 1.5 |
| Sin suavizado | 0.972 | 0.953 | 0.962 | 82 ms | 1.3 |

> Son datos **sintéticos**: sirven para comparar variantes del detector y elegir parámetros de forma razonada, no para afirmar cómo se comportará con cualquier mano real.
