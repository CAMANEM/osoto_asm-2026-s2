#!/usr/bin/env python3
"""
host/radar_serial.py

Lee una captura del Arduino (comando Serial 'D') y estima el retardo
del eco con la correlación directa y la correlación por FFT propias
del proyecto (Partes 2–3), calculando la distancia monostática.

Uso:
  1) Sube firmware/acoustic_radar/acoustic_radar.ino
  2) En Serial Monitor: M  (medir) luego D (dump), o:
  3) python host/radar_serial.py --port /dev/ttyACM0

También acepta un archivo de dump guardado:
  python host/radar_serial.py --file captura.txt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Permitir importar módulos del proyecto desde host/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generation.signal_generator import AcousticSignalGenerator
from signal_processing.correlator import EchoCorrelator


def parse_dump_text(text: str) -> tuple[dict, np.ndarray]:
    """
    Parsea el bloque BEGIN_SAMPLES ... END_SAMPLES del firmware.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    meta: dict = {}
    values: list[float] = []
    inside = False

    for ln in lines:
        if ln == "BEGIN_SAMPLES":
            inside = True
            values.clear()
            meta.clear()
            continue
        if ln == "END_SAMPLES":
            inside = False
            break
        if not inside:
            continue
        if "=" in ln and not ln[0].lstrip("-").isdigit():
            key, val = ln.split("=", 1)
            meta[key] = float(val) if "." in val else int(val)
        else:
            values.append(float(ln))

    if not values:
        raise ValueError("No se encontraron muestras en el dump.")
    return meta, np.asarray(values, dtype=float)


def read_from_serial(port: str, baud: int = 9600, timeout_s: float = 8.0) -> str:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Falta pyserial. Instala con: pip install pyserial"
        ) from exc

    with serial.Serial(port, baud, timeout=1) as ser:
        time.sleep(2.0)  # reset USB del Uno
        ser.reset_input_buffer()
        ser.write(b"M\n")
        time.sleep(0.8)
        ser.write(b"D\n")

        buf = ""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            chunk = ser.read(ser.in_waiting or 1).decode("utf-8", errors="ignore")
            if chunk:
                buf += chunk
            if "END_SAMPLES" in buf:
                break
            time.sleep(0.05)
    return buf


def estimate_distance(
    received: np.ndarray,
    fs: float,
    f0: float,
    blank_ms: float,
    min_lag: int,
    pulse_ms: float = 5.0,
) -> dict:
    gen = AcousticSignalGenerator(fs)
    reference = gen.generate_pulse(pulse_ms / 1000.0, f0)
    correlator = EchoCorrelator(fs)

    lags_d, corr_d = correlator.correlate_direct(reference, received)
    lags_f, corr_f = correlator.correlate_fft(reference, received)

    # Ignorar acoplamiento directo: solo lags >= min_lag
    def peak_from(lags: np.ndarray, corr: np.ndarray) -> tuple[int, float, float]:
        mask = lags >= min_lag
        if not np.any(mask):
            raise ValueError("min_lag fuera de rango de correlación.")
        idx_local = int(np.argmax(np.abs(corr[mask])))
        idxs = np.flatnonzero(mask)
        idx = int(idxs[idx_local])
        lag = int(lags[idx])
        tau = blank_ms / 1000.0 + lag / fs
        dist = 343.0 * tau / 2.0
        return lag, tau, dist

    lag_d, tau_d, dist_d = peak_from(lags_d, corr_d)
    lag_f, tau_f, dist_f = peak_from(lags_f, corr_f)

    return {
        "lag_direct": lag_d,
        "tau_direct_s": tau_d,
        "dist_direct_m": dist_d,
        "lag_fft": lag_f,
        "tau_fft_s": tau_f,
        "dist_fft_m": dist_f,
        "lags_direct": lags_d,
        "corr_direct": corr_d,
        "lags_fft": lags_f,
        "corr_fft": corr_f,
        "reference": reference,
        "received": received,
    }


def save_figures(result: dict, out_dir: Path, fs: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    t = np.arange(result["received"].size) / fs

    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(t * 1000.0, result["received"])
    ax.set_xlabel("Tiempo [ms]")
    ax.set_ylabel("ADC (centrado)")
    ax.set_title("Señal recibida (captura Arduino)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "parte4_senal_recibida.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(result["lags_direct"], result["corr_direct"], label="Directa")
    ax.plot(result["lags_fft"], result["corr_fft"], "--", label="FFT")
    ax.axvline(result["lag_fft"], color="r", alpha=0.5, label="Pico")
    ax.set_xlabel("Lag [muestras]")
    ax.set_ylabel("Correlación")
    ax.set_title("Correlación cruzada (host, FFT propia)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "parte4_correlacion.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Host radar acústico Parte 4")
    parser.add_argument("--port", type=str, default=None, help="Puerto Serial, ej. /dev/ttyACM0")
    parser.add_argument("--file", type=str, default=None, help="Archivo de dump Serial")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--out",
        type=str,
        default=str(ROOT / "outputs" / "images_parte4"),
        help="Carpeta de figuras",
    )
    args = parser.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="ignore")
    elif args.port:
        print(f"Leyendo de {args.port} ...")
        text = read_from_serial(args.port, args.baud)
    else:
        raise SystemExit("Indica --port /dev/ttyACM0  o  --file captura.txt")

    meta, received = parse_dump_text(text)
    fs = float(meta.get("FS", 8000))
    f0 = float(meta.get("F0", 3000))
    blank_ms = float(meta.get("BLANK_MS", 1))
    min_lag = int(meta.get("MIN_LAG", 8))

    # El dump del firmware ya viene sin DC si se hizo tras removeDc
    result = estimate_distance(received, fs, f0, blank_ms, min_lag)
    save_figures(result, Path(args.out), fs)

    print("=== Resultado host (correlación Python) ===")
    print(f"FS={fs} Hz  F0={f0} Hz  blank={blank_ms} ms  min_lag={min_lag}")
    print(
        f"Directa: lag={result['lag_direct']}  "
        f"tau={result['tau_direct_s']*1000:.3f} ms  "
        f"d={result['dist_direct_m']*100:.1f} cm"
    )
    print(
        f"FFT:     lag={result['lag_fft']}  "
        f"tau={result['tau_fft_s']*1000:.3f} ms  "
        f"d={result['dist_fft_m']*100:.1f} cm"
    )
    print(f"Figuras en: {args.out}")


if __name__ == "__main__":
    main()
