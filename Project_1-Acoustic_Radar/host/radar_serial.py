#!/usr/bin/env python3
"""
host/radar_serial.py

Lee una captura del Arduino (comando Serial 'D') y estima el retardo
del eco con la correlación directa y la correlación por FFT propias
del proyecto (Partes 2–3), según la teoría del curso:

    r = IFFT( conj(FFT(ref_chirp)) * FFT(rx) )

La señal de referencia es un chirp lineal (misma f0, f1 y duración que
el firmware), no un tono corto.

Uso:
  1) Sube firmware/acoustic_radar/acoustic_radar.ino
  2) En Serial Monitor: M  (medir) luego D (dump), o:
  3) python host/radar_serial.py --port COM3   (Windows)
     python host/radar_serial.py --port /dev/ttyACM0

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

SPEED_OF_SOUND_M_S = 343.0


def parse_dump_text(text: str) -> tuple[dict, np.ndarray]:
    """
    Parsea el bloque BEGIN_SAMPLES ... END_SAMPLES del firmware.
    Metadatos: líneas KEY=VALUE; el resto son muestras ADC centradas.
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
        if "=" in ln and not ln.lstrip("-").replace(".", "", 1).isdigit():
            key, val = ln.split("=", 1)
            meta[key] = float(val) if "." in val else int(val)
        else:
            values.append(float(ln))

    if not values:
        raise ValueError("No se encontraron muestras en el dump.")
    return meta, np.asarray(values, dtype=float)


def read_from_serial(port: str, baud: int = 9600, timeout_s: float = 12.0) -> str:
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
        time.sleep(1.2)  # chirp 10 ms + correlación onboard
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
    f_start: float,
    f_end: float,
    chirp_ms: float,
    min_lag: int,
) -> dict:
    """
    Réplica la Parte 3 del adelanto sobre una captura real:
    referencia = chirp lineal; retardo = argmax |correlación|;
    d = (vs * tau) / 2.
    """
    gen = AcousticSignalGenerator(fs)
    reference = gen.generate_chirp(
        duration_seconds=chirp_ms / 1000.0,
        start_freq_hz=f_start,
        end_freq_hz=f_end,
    )
    correlator = EchoCorrelator(fs)

    lags_d, corr_d = correlator.correlate_direct(reference, received)
    lags_f, corr_f = correlator.correlate_fft(reference, received)

    def peak_from(lags: np.ndarray, corr: np.ndarray) -> tuple[int, float, float, float]:
        mask = lags >= min_lag
        if not np.any(mask):
            raise ValueError("min_lag fuera de rango de correlación.")
        idx_local = int(np.argmax(np.abs(corr[mask])))
        idxs = np.flatnonzero(mask)
        idx = int(idxs[idx_local])
        lag = int(lags[idx])
        tau = lag / fs
        dist = SPEED_OF_SOUND_M_S * tau / 2.0
        peak = float(corr[idx])
        return lag, tau, dist, peak

    lag_d, tau_d, dist_d, peak_d = peak_from(lags_d, corr_d)
    lag_f, tau_f, dist_f, peak_f = peak_from(lags_f, corr_f)

    return {
        "lag_direct": lag_d,
        "tau_direct_s": tau_d,
        "dist_direct_m": dist_d,
        "peak_direct": peak_d,
        "lag_fft": lag_f,
        "tau_fft_s": tau_f,
        "dist_fft_m": dist_f,
        "peak_fft": peak_f,
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
    t_ref = np.arange(result["reference"].size) / fs

    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(t_ref * 1000.0, result["reference"])
    ax.set_xlabel("Tiempo [ms]")
    ax.set_ylabel("Amplitud")
    ax.set_title("Señal de referencia (chirp lineal)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "parte4_chirp_referencia.png", dpi=150)
    plt.close(fig)

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
    ax.plot(
        result["lags_direct"] / fs * 1000.0,
        result["corr_direct"],
        label="Directa",
    )
    ax.plot(
        result["lags_fft"] / fs * 1000.0,
        result["corr_fft"],
        "--",
        label="FFT",
    )
    ax.axvline(
        result["lag_fft"] / fs * 1000.0,
        color="r",
        alpha=0.5,
        label=f"Pico FFT ({result['lag_fft']} muestras)",
    )
    ax.set_xlabel("Retardo [ms]")
    ax.set_ylabel("Correlación")
    ax.set_title("Correlación cruzada (host, FFT propia — teoría del curso)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "parte4_correlacion.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Host radar acústico: chirp + correlación FFT (Parte 4)"
    )
    parser.add_argument("--port", type=str, default=None, help="Puerto Serial, ej. COM3")
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
        raise SystemExit("Indica --port COM3  o  --file captura.txt")

    meta, received = parse_dump_text(text)
    fs = float(meta.get("FS", 8000))
    f_start = float(meta.get("F_START", meta.get("F0", 2000)))
    f_end = float(meta.get("F_END", 3500))
    chirp_ms = float(meta.get("CHIRP_MS", 5))
    min_lag = int(meta.get("MIN_LAG", 10))

    result = estimate_distance(received, fs, f_start, f_end, chirp_ms, min_lag)
    save_figures(result, Path(args.out), fs)

    print("=== Resultado host (chirp + correlación Python) ===")
    print(
        f"FS={fs} Hz  chirp={chirp_ms} ms  "
        f"f={f_start:.0f}→{f_end:.0f} Hz  min_lag={min_lag}"
    )
    print(
        f"Directa: lag={result['lag_direct']}  "
        f"tau={result['tau_direct_s']*1000:.3f} ms  "
        f"d={result['dist_direct_m']*100:.1f} cm  "
        f"peak={result['peak_direct']:.1f}"
    )
    print(
        f"FFT:     lag={result['lag_fft']}  "
        f"tau={result['tau_fft_s']*1000:.3f} ms  "
        f"d={result['dist_fft_m']*100:.1f} cm  "
        f"peak={result['peak_fft']:.1f}"
    )
    print(f"Figuras en: {args.out}")


if __name__ == "__main__":
    main()
