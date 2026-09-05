# Taller Semana 5 — Experimentación de detección de ecos

Código de apoyo para el **Taller de Proyecto Individual 1** (CE1110 —
Análisis de Señales Mixtas), que cubre la **Parte 2 (experimentos con
FFT)** y la **Parte 3 (experimentos de detección de ecos)** del enunciado
del Proyecto Individual 1 (radar acústico).

## Estructura del proyecto

```
radar_acustico/
├── signal_processing/
│   ├── fourier_transform.py   # DFT y FFT (Cooley-Tukey) propias
│   └── correlator.py          # Correlación cruzada directa y por FFT
├── generation/
│   └── signal_generator.py    # Pulsos, chirps, ecos simulados, ruido
├── benchmarking/
│   └── benchmark.py           # Comparación de tiempos DFT/FFT y correlación
├── visualization/
│   └── visualizer.py          # Generación y guardado de gráficas
├── main_parte2_fft.py         # Orquesta la Parte 2
├── main_parte3_ecos.py        # Orquesta la Parte 3
└── main.py                    # Ejecuta ambas partes
```

## Requerimientos

```bash
numpy>=1.24
matplotlib>=3.7
```

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
# Ejecuta ambas partes:
python main.py

# O cada parte por separado:
python main_parte2_fft.py
python main_parte3_ecos.py
```

Las imágenes generadas ("recopilación de imágenes con los efectos
principales" que pide el enunciado) se guardan automáticamente en
`outputs/images/`.

## Qué cubre cada parte

**Parte 2 — Experimentos con FFT**
- Implementación propia de DFT (fuerza bruta, O(N²)) y FFT
  (Cooley-Tukey, O(N log N)), sin usar `numpy.fft` internamente.
- Comparación de tiempos de ejecución DFT vs. FFT para N = 64…4096.
- Magnitud y fase de un tono puro, una señal multi-tono y un chirp.

**Parte 3 — Experimentos de detección de ecos**
- Generación de una señal transmitida (chirp) y un eco simulado con
  retardo y atenuación conocidos, más ruido gaussiano.
- Correlación cruzada directa (definición en el tiempo).
- Correlación cruzada acelerada por FFT (teorema de convolución).
- Estimación del retardo (tiempo de vuelo) y de la distancia
  equivalente (`d = v_s·τ/2`).
- Comparación de tiempos entre ambas implementaciones de correlación.

## Notas de diseño

- Paradigma orientado a objetos: cada responsabilidad (transformadas,
  correlación, generación de señales, benchmarking, visualización) vive
  en su propia clase con estado y comportamiento cohesivos.
- Docstrings en estilo Javadoc (`@param`, `@return`, `@throws`) para
  facilitar la trazabilidad de cada método.
- Sin dependencia de `numpy.fft` en la lógica de transformada: la DFT y
  la FFT son implementaciones propias, tal como exige el enunciado.
