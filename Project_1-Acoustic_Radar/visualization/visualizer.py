"""
visualizer.py

Generación y persistencia de las gráficas requeridas por el enunciado
("recopilación de imágenes con los efectos principales"): señales en el
tiempo, magnitud/fase en frecuencia, comparaciones de desempeño y
resultados de correlación para la estimación del retardo del eco.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")  # Backend sin interfaz gráfica, apto para servidores.
import matplotlib.pyplot as plt
import numpy as np

from benchmarking.benchmark import BenchmarkResult
from signal_processing.correlator import DelayEstimate


class SignalVisualizer:
    """
    Encapsula la lógica de graficación y guardado de figuras en disco,
    centralizando el estilo visual y la carpeta de salida utilizados por
    todos los experimentos del taller.
    """

    def __init__(self, output_directory: str) -> None:
        """
        @param output_directory Ruta de la carpeta donde se guardarán las
                                imágenes generadas. Se crea si no existe.
        """
        self._output_directory = output_directory
        os.makedirs(self._output_directory, exist_ok=True)

    def _save_figure(self, figure: plt.Figure, filename: str) -> str:
        """
        Guarda una figura de matplotlib en la carpeta de salida y libera
        sus recursos.

        @param  figure   Figura de matplotlib a guardar.
        @param  filename Nombre del archivo de salida (incluye extensión).
        @return           Ruta completa del archivo guardado.
        """
        full_path = os.path.join(self._output_directory, filename)
        figure.tight_layout()
        figure.savefig(full_path, dpi=150)
        plt.close(figure)
        return full_path

    def plot_time_domain(
        self, t: np.ndarray, signal: np.ndarray, title: str, filename: str
    ) -> str:
        """
        Grafica una señal en el dominio del tiempo.

        @param  t        Vector de tiempo (s).
        @param  signal   Señal a graficar.
        @param  title    Título de la gráfica.
        @param  filename Nombre de archivo de salida.
        @return           Ruta del archivo guardado.
        """
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(t, signal, linewidth=1.0)
        ax.set_title(title)
        ax.set_xlabel("Tiempo [s]")
        ax.set_ylabel("Amplitud")
        ax.grid(True, alpha=0.3)
        return self._save_figure(fig, filename)

    def plot_magnitude_phase(
        self,
        freqs: np.ndarray,
        spectrum: np.ndarray,
        title: str,
        filename: str,
    ) -> str:
        """
        Grafica la magnitud y la fase de un espectro complejo en dos
        subgráficas apiladas, solo para frecuencias no negativas.

        @param  freqs    Eje de frecuencias (Hz), típicamente proveniente
                         de {@link FourierTransform#frequency_bins}.
        @param  spectrum Espectro complejo asociado a `freqs`.
        @param  title    Título general de la figura.
        @param  filename Nombre de archivo de salida.
        @return           Ruta del archivo guardado.
        """
        half = len(freqs) // 2
        freqs_pos = freqs[:half]
        magnitude = np.abs(spectrum[:half])
        phase = np.angle(spectrum[:half])

        fig, (ax_mag, ax_phase) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

        ax_mag.plot(freqs_pos, magnitude, color="tab:blue")
        ax_mag.set_ylabel("Magnitud |X(f)|")
        ax_mag.set_title(title)
        ax_mag.grid(True, alpha=0.3)

        ax_phase.plot(freqs_pos, phase, color="tab:orange")
        ax_phase.set_ylabel("Fase [rad]")
        ax_phase.set_xlabel("Frecuencia [Hz]")
        ax_phase.grid(True, alpha=0.3)

        return self._save_figure(fig, filename)

    def plot_benchmark_comparison(
        self, result: BenchmarkResult, title: str, filename: str
    ) -> str:
        """
        Grafica en escala log-log el tiempo de ejecución de la
        implementación de referencia contra la implementación acelerada,
        en función del tamaño de entrada N.

        @param  result   Resultado de comparación
                         ({@link BenchmarkResult}) a graficar.
        @param  title    Título de la gráfica.
        @param  filename Nombre de archivo de salida.
        @return           Ruta del archivo guardado.
        """
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.plot(result.sizes, result.times_slow, "o-", label="Implementación directa")
        ax.plot(result.sizes, result.times_fast, "s-", label="Implementación FFT")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xlabel("Tamaño N")
        ax.set_ylabel("Tiempo promedio [s]")
        ax.set_title(title)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
        return self._save_figure(fig, filename)

    def plot_correlation(
        self,
        estimate: DelayEstimate,
        sampling_rate: float,
        title: str,
        filename: str,
    ) -> str:
        """
        Grafica la función de correlación cruzada completa y resalta el
        pico utilizado para estimar el retardo del eco.

        @param  estimate      Resultado de la estimación de retardo
                              ({@link DelayEstimate}).
        @param  sampling_rate Frecuencia de muestreo (Hz), usada para
                              expresar el eje de retardo en segundos.
        @param  title         Título de la gráfica.
        @param  filename      Nombre de archivo de salida.
        @return                Ruta del archivo guardado.
        """
        lag_seconds_axis = estimate.lags / sampling_rate

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(lag_seconds_axis, estimate.correlation, linewidth=1.0)
        ax.axvline(
            estimate.lag_seconds,
            color="red",
            linestyle="--",
            label=f"Retardo estimado = {estimate.lag_seconds * 1000:.2f} ms",
        )
        ax.set_title(title)
        ax.set_xlabel("Retardo [s]")
        ax.set_ylabel("Correlación cruzada")
        ax.grid(True, alpha=0.3)
        ax.legend()
        return self._save_figure(fig, filename)
