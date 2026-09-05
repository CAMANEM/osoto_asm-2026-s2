"""
main_parte3_ecos.py

Orquesta los experimentos de la Parte 3 del enunciado ("Experimentos de
detección de ecos"): generación de señal transmitida y ecos simulados,
estimación del retardo mediante correlación directa y mediante FFT, y
comparación de desempeño entre ambas implementaciones.

Uso:
    python main_parte3_ecos.py
"""

from __future__ import annotations

import logging

from benchmarking.benchmark import PerformanceBenchmark
from generation.signal_generator import AcousticSignalGenerator, EchoDefinition
from signal_processing.correlator import EchoCorrelator
from visualization.visualizer import SignalVisualizer

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SPEED_OF_SOUND_M_S = 343.0  # Velocidad del sonido en el aire a ~20 C.


class EchoDetectionExperiment:
    """
    Agrupa la lógica de la Parte 3 del proyecto: simulación de la señal
    transmitida y su eco, detección del retardo mediante correlación
    cruzada (directa y por FFT) y cálculo de la distancia estimada al
    objeto reflectante, replicando en software la etapa de procesamiento
    del radar acústico.
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
        self._correlator = EchoCorrelator(sampling_rate)
        self._visualizer = SignalVisualizer(output_directory)

    @staticmethod
    def _distance_from_delay(delay_seconds: float) -> float:
        """
        Calcula la distancia al objeto reflectante a partir del tiempo de
        vuelo, para una configuración monostática:

            d = (v_s * tau) / 2

        @param  delay_seconds Tiempo de vuelo estimado (tau), en segundos.
        @return                Distancia estimada al objeto, en metros.
        """
        return (SPEED_OF_SOUND_M_S * delay_seconds) / 2.0

    def run(self) -> None:
        """
        Ejecuta la Parte 3 completa: genera la señal transmitida y una
        señal recibida sintética con un eco de retardo conocido y ruido,
        estima el retardo con ambos métodos de correlación, calcula la
        distancia resultante y compara el desempeño de las dos
        implementaciones.
        """
        logger.info("=== Parte 3: Experimentos de detección de ecos ===")

        # 1. Señal transmitida conocida (chirp, fácil de identificar por
        #    correlación gracias a su ancho de banda).
        transmitted = self._generator.generate_chirp(
            duration_seconds=0.005, start_freq_hz=2_000.0, end_freq_hz=8_000.0
        )

        # 2. Eco simulado: retardo conocido (equivalente a una distancia
        #    conocida) con atenuación y ruido de fondo.
        true_delay_seconds = 0.006  # 6 ms de tiempo de vuelo.
        echo = EchoDefinition(delay_seconds=true_delay_seconds, attenuation=0.4)
        received = self._generator.build_received_signal(
            transmitted_signal=transmitted,
            echoes=[echo],
            total_duration_seconds=0.02,
            noise_std=0.05,
            random_seed=7,
        )

        expected_distance = self._distance_from_delay(true_delay_seconds)
        logger.info(
            "Retardo real simulado: %.3f ms (distancia real equivalente: %.3f m)",
            true_delay_seconds * 1000,
            expected_distance,
        )

        # 3. Graficar la señal transmitida y la señal recibida.
        t_tx = self._generator.time_vector(len(transmitted) / self._sampling_rate)
        self._visualizer.plot_time_domain(
            t_tx,
            transmitted,
            title="Señal transmitida (chirp)",
            filename="parte3_senal_transmitida.png",
        )

        t_rx = self._generator.time_vector(len(received) / self._sampling_rate)
        self._visualizer.plot_time_domain(
            t_rx,
            received,
            title="Señal recibida (con eco y ruido)",
            filename="parte3_senal_recibida.png",
        )

        # 4. Correlación directa.
        lags_direct, corr_direct = self._correlator.correlate_direct(
            transmitted, received
        )
        estimate_direct = self._correlator.estimate_delay(lags_direct, corr_direct)

        # 5. Correlación mediante FFT.
        lags_fft, corr_fft = self._correlator.correlate_fft(transmitted, received)
        estimate_fft = self._correlator.estimate_delay(lags_fft, corr_fft)

        for label, estimate in (
            ("directa", estimate_direct),
            ("FFT", estimate_fft),
        ):
            distance = self._distance_from_delay(estimate.lag_seconds)
            logger.info(
                "Correlación %s -> retardo estimado = %.3f ms | "
                "distancia estimada = %.3f m",
                label,
                estimate.lag_seconds * 1000,
                distance,
            )

        self._visualizer.plot_correlation(
            estimate_direct,
            self._sampling_rate,
            title="Correlación cruzada directa",
            filename="parte3_correlacion_directa.png",
        )
        self._visualizer.plot_correlation(
            estimate_fft,
            self._sampling_rate,
            title="Correlación cruzada mediante FFT",
            filename="parte3_correlacion_fft.png",
        )

        # 6. Comparación de desempeño entre ambas implementaciones.
        benchmark = PerformanceBenchmark(num_trials=3)
        sizes = [64, 128, 256, 512, 1024]
        bench_result = benchmark.compare_correlation_methods(
            sizes, sampling_rate=self._sampling_rate
        )

        for n, t_direct, t_fft, speedup in zip(
            bench_result.sizes,
            bench_result.times_slow,
            bench_result.times_fast,
            bench_result.speedup,
        ):
            logger.info(
                "N=%5d | Correlación directa=%.6f s | Correlación FFT=%.6f s | "
                "speedup=%.1fx",
                n,
                t_direct,
                t_fft,
                speedup,
            )

        self._visualizer.plot_benchmark_comparison(
            bench_result,
            title="Comparación de tiempos: Correlación directa vs FFT",
            filename="parte3_benchmark_correlacion.png",
        )

        logger.info("Parte 3 completada. Imágenes guardadas en outputs/images/.")


if __name__ == "__main__":
    EchoDetectionExperiment().run()
