# Proyecto Individual 1 — Radar acústico (CE1110)

Código para las **Partes 2–3** (simulación Python) y la **Parte 4**
(implementación en Arduino Uno + host de correlación FFT).

## Estructura

```
Project_1-Acoustic_Radar/
├── signal_processing/          # DFT/FFT propias + correlación
├── generation/                 # Pulsos, chirps, ecos sintéticos
├── benchmarking/
├── visualization/
├── firmware/acoustic_radar/    # Sketch Arduino Uno (Parte 4–5)
├── host/radar_serial.py        # Lee Serial y correlaciona con FFT propia
├── main_parte2_fft.py
├── main_parte3_ecos.py
└── main.py
```

## Partes 2 y 3 (Python)

```bash
pip install -r requirements.txt
python main.py
# o:
python main_parte2_fft.py
python main_parte3_ecos.py
```

Figuras → `outputs/images/`.

## Parte 4 — Microcontrolador

### Hardware
- **TX:** D9 → 1 kΩ → Base 2N2222; Emitter → GND; Collector → parlante → 47–100 Ω → 5V
- **RX:** Electret + LM358 (Circuit Basics) → A0
- GND común

### Firmware
1. Abre `firmware/acoustic_radar/acoustic_radar.ino` en Arduino IDE.
2. Sube al Uno.
3. Serial Monitor a **9600 baud**.
4. Al arrancar entra en **modo continuo** (mide en bucle + filtro EMA).
5. Abre **Serial Plotter** (9600) para ver `raw_cm` y `filt_cm` en vivo.
6. Comandos: `C` continuo ON · `X` parar · `M` detalle · `D` dump CSV · `S` OFF.

Salida continua (Serial Plotter):

```
raw_cm:52.1,filt_cm:50.8,lag:47,peak:...
raw_cm:49.3,filt_cm:50.2,lag:46,peak:...
```

### Host Python (correlación FFT — teoría Partes 2–3)

El host reconstruye el mismo chirp lineal y aplica:

`r = IFFT( conj(FFT(ref)) * FFT(rx) )`

con la FFT propia del proyecto (`signal_processing/`).

```bash
# Windows (ejemplo):
python host/radar_serial.py --port COM3
# Linux:
python host/radar_serial.py --port /dev/ttyACM0
```

O pega el dump Serial en un archivo:

```bash
python host/radar_serial.py --file captura.txt
```

Figuras → `outputs/images_parte4/` (chirp de referencia, RX, correlación directa vs FFT).

### Prueba de defensa (rápida)
1. Objeto rígido (caja/libro) a **~50 cm** y luego **~100 cm**.
2. Mic y parlante juntos, apuntando al objeto (no uno contra el otro).
3. Ambiente quieto.
4. Compara `distancia_cm` al mover el objeto: debe cambiar en el sentido correcto
   (no esperes precisión de cm exactos en el MVP).

### Parámetros ajustables en el `.ino`
| Constante        | Default | Efecto                                              |
|------------------|---------|-----------------------------------------------------|
| `F_START_HZ`     | 2000    | Inicio del chirp lineal (Hz)                        |
| `F_END_HZ`       | 7000    | Fin del chirp (bajo Nyquist a 16 kHz)               |
| `CHIRP_MS`       | 10      | Duración del chirp (más largo que el tono de 1 ms)  |
| `MIN_LAG`        | 24      | Ignora acoplamiento directo (~1.5 ms)               |
| `N_SAMPLES`      | 320     | Ventana RX (~20 ms ≈ hasta ~3.4 m teóricos)         |
| `FS_HZ`          | 16000   | Muestreo (coherente con `SAMPLE_US=62`)             |
