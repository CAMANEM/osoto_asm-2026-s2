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
4. Envía `M` + Enter → una medición (FFT peak + correlación + distancia).
5. Envía `D` + Enter → dump CSV de la última captura.

Salida típica:

```
--- Medicion ---
FFT_peak_Hz=3000.0
lag_samples=23
corr_peak=...
tau_ms=3.875
distancia_cm=66.5
distancia_m=0.665
OK
```

### Host Python (correlación FFT con tu código de Partes 2–3)

```bash
# Detecta el puerto (Linux): ls /dev/ttyACM*  o  /dev/ttyUSB*
python host/radar_serial.py --port /dev/ttyACM0
```

O pega el dump Serial en un archivo:

```bash
python host/radar_serial.py --file captura.txt
```

Figuras → `outputs/images_parte4/`.

### Prueba de defensa (rápida)
1. Objeto rígido (caja/libro) a **~50 cm** y luego **~100 cm**.
2. Mic y parlante juntos, apuntando al objeto (no uno contra el otro).
3. Ambiente quieto.
4. Compara `distancia_cm` al mover el objeto: debe cambiar en el sentido correcto
   (no esperes precisión de cm exactos en el MVP).

### Parámetros ajustables en el `.ino`
| Constante   | Default | Efecto                                      |
|-------------|---------|---------------------------------------------|
| `F0_HZ`     | 3000    | Frecuencia del pulso TX                     |
| `BLANK_MS`  | 1       | Espera antes de muestrear                   |
| `MIN_LAG`   | 8       | Ignora acoplamiento directo (~1 ms)         |
| `N_SAMPLES` | 256     | Ventana RX (~32 ms ≈ hasta ~5 m teóricos)   |
| `FS_HZ`     | 8000    | Muestreo (coherente con `SAMPLE_US=125`)    |
