"""
main_parte2_fft.py

Orquesta los experimentos de la Parte 2 del enunciado ("Experimentos con
FFT"): comparación de tiempos DFT vs. FFT, y representación de magnitud y
fase para distintas señales.

Uso:
    python main_parte2_fft.py
"""

from __future__ import annotations

import logging

from benchmarking.benchmark import PerformanceBenchmark
from generation.signal_generator import AcousticSignalGenerator
from signal_processing.fourier_transform import FourierTransform
from visualization.visualizer import SignalVisualizer

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class FftExperiment:
    """
    Agrupa la lógica de la Parte 2 del proyecto: implementación propia de
    DFT/FFT aplicada a señales de prueba, comparación de tiempos de
    ejecución para distintos tamaños de N, y visualización de magnitud y
    fase.
    """

    def __init__(
        self,
        sampling_rate: float = 44_100.0,
        output_directory: str = "outputs/images",
    ) -> None:
        """
        @param sampling_rate    Frecuencia de muestreo en Hz.
        @param output_directory Carpeta donde se guardan las imágenes
                                generadas por el experimento.
        """
        self._sampling_rate = sampling_rate
        self._generator = AcousticSignalGenerator(sampling_rate)
        self._visualizer = SignalVisualizer(output_directory)

    def _analyze_signal(self, signal, label: str, filename_prefix: str) -> None:
        """
        Calcula la FFT propia de una señal, la grafica en magnitud/fase y
        deja constancia en el log del resultado, incluyendo una
        verificación cruzada frente a la DFT directa para señales cortas.

        @param signal          Señal en el dominio del tiempo a analizar.
        @param label           Nombre descriptivo de la señal (para
                               títulos y logs).
        @param filename_prefix Prefijo usado para nombrar los archivos de
                               imagen generados.
        """
        padded_signal = FourierTransform.zero_pad_to_power_of_two(signal)
        spectrum = FourierTransform.fft(padded_signal)
        freqs = FourierTransform.frequency_bins(
            len(padded_signal), self._sampling_rate
        )

        self._visualizer.plot_magnitude_phase(
            freqs,
            spectrum,
            title=f"Magnitud y fase - {label}",
            filename=f"{filename_prefix}_magnitud_fase.png",
        )

        t = self._generator.time_vector(len(signal) / self._sampling_rate)
        self._visualizer.plot_time_domain(
            t,
            signal,
            title=f"Señal en el tiempo - {label}",
            filename=f"{filename_prefix}_tiempo.png",
        )

        dominant_bin = int(
            FourierTransform.magnitude(spectrum)[: len(spectrum) // 2].argmax()
        )
        dominant_freq = freqs[dominant_bin]
        logger.info(
            "Señal '%s': frecuencia dominante detectada ~= %.2f Hz",
            label,
            dominant_freq,
        )

    def run(self) -> None:
        """
        Ejecuta la Parte 2 completa: genera señales de prueba (tono puro,
        combinación de tonos y chirp), analiza su espectro y compara el
        tiempo de ejecución de la DFT directa frente a la FFT propia para
        distintos tamaños de N.
        """
        logger.info("=== Parte 2: Experimentos con FFT ===")

        # 1. Señal de tono puro.
        pure_tone = self._generator.generate_pulse(
            duration_seconds=0.02, frequency_hz=1_000.0
        )
        self._analyze_signal(pure_tone, "Tono puro 1 kHz", "parte2_tono_puro")

        # 2. Señal multi-tono (superposición de dos frecuencias).
        tone_a = self._generator.generate_pulse(0.02, 1_000.0, amplitude=1.0)
        tone_b = self._generator.generate_pulse(0.02, 3_000.0, amplitude=0.5)
        multi_tone = tone_a + tone_b
        self._analyze_signal(multi_tone, "Multi-tono 1kHz + 3kHz", "parte2_multitono")

        # 3. Señal chirp (barrido de frecuencia), candidata a señal
        #    transmitida por el radar acústico.
        chirp = self._generator.generate_chirp(
            duration_seconds=0.02, start_freq_hz=500.0, end_freq_hz=5_000.0
        )
        self._analyze_signal(chirp, "Chirp 500 Hz - 5 kHz", "parte2_chirp")

        # 4. Comparación de tiempos de ejecución DFT vs. FFT.
        benchmark = PerformanceBenchmark(num_trials=3)
        sizes = [64, 128, 256, 512, 1024, 2048, 4096]
        result = benchmark.compare_dft_fft(sizes)

        for n, t_dft, t_fft, speedup in zip(
            result.sizes, result.times_slow, result.times_fast, result.speedup
        ):
            logger.info(
                "N=%5d | DFT=%.6f s | FFT=%.6f s | speedup=%.1fx",
                n,
                t_dft,
                t_fft,
                speedup,
            )

        self._visualizer.plot_benchmark_comparison(
            result,
            title="Comparación de tiempos: DFT vs FFT",
            filename="parte2_benchmark_dft_vs_fft.png",
        )

        logger.info("Parte 2 completada. Imágenes guardadas en outputs/images/.")


if __name__ == "__main__":
    FftExperiment().run()
