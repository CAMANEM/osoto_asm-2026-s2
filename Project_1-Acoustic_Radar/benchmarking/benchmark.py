"""
benchmark.py

Utilidades para medir y comparar el tiempo de ejecución de las
implementaciones directa (fuerza bruta) y acelerada (FFT) tanto de la
transformada de Fourier como de la correlación cruzada, requeridas por las
partes 2.b y 3.d del enunciado del proyecto.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from signal_processing.fourier_transform import FourierTransform
from signal_processing.correlator import EchoCorrelator


@dataclass
class BenchmarkResult:
    """
    Contenedor de resultados de una comparación de desempeño entre dos
    implementaciones equivalentes (por ejemplo, DFT vs. FFT).

    @field sizes      Tamaños de entrada (N) evaluados.
    @field times_slow Tiempos promedio (s) de la implementación de
                      referencia (más lenta).
    @field times_fast Tiempos promedio (s) de la implementación acelerada.
    @field speedup    Factor de aceleración (times_slow / times_fast) por
                      cada tamaño.
    """

    sizes: list[int] = field(default_factory=list)
    times_slow: list[float] = field(default_factory=list)
    times_fast: list[float] = field(default_factory=list)
    speedup: list[float] = field(default_factory=list)


class PerformanceBenchmark:
    """
    Ejecuta y organiza las comparaciones de tiempo de ejecución solicitadas
    en el enunciado: DFT vs. FFT (parte 2.b) y correlación directa vs.
    correlación por FFT (parte 3.d).
    """

    def __init__(self, num_trials: int = 3, random_seed: int | None = 42) -> None:
        """
        @param num_trials  Número de repeticiones por tamaño para promediar
                           el tiempo medido y reducir el ruido de medición.
        @param random_seed Semilla para generar señales de prueba
                           reproducibles.
        @throws ValueError si num_trials es menor a 1.
        """
        if num_trials < 1:
            raise ValueError("num_trials debe ser al menos 1.")
        self._num_trials = num_trials
        self._rng = np.random.default_rng(random_seed)

    @staticmethod
    def _time_callable(func: Callable[[], object]) -> float:
        """
        Mide el tiempo de ejecución de una función sin argumentos.

        @param  func Función a cronometrar (invocada sin argumentos).
        @return       Tiempo transcurrido en segundos.
        """
        start = time.perf_counter()
        func()
        return time.perf_counter() - start

    def compare_dft_fft(self, sizes: list[int]) -> BenchmarkResult:
        """
        Compara el tiempo de ejecución de la DFT directa (O(N^2)) contra
        la FFT propia (O(N log N)) para distintos tamaños de señal.

        @param  sizes Lista de tamaños N (se recomienda que sean potencias
                      de 2, ya que la FFT propia lo requiere).
        @return        Objeto {@link BenchmarkResult} con los tiempos
                       promedio y el factor de aceleración por tamaño.
        """
        result = BenchmarkResult()

        for n_samples in sizes:
            test_signal = self._rng.normal(size=n_samples)

            dft_times = [
                self._time_callable(lambda: FourierTransform.dft(test_signal))
                for _ in range(self._num_trials)
            ]
            fft_times = [
                self._time_callable(lambda: FourierTransform.fft(test_signal))
                for _ in range(self._num_trials)
            ]

            avg_dft = float(np.mean(dft_times))
            avg_fft = float(np.mean(fft_times))

            result.sizes.append(n_samples)
            result.times_slow.append(avg_dft)
            result.times_fast.append(avg_fft)
            result.speedup.append(avg_dft / avg_fft if avg_fft > 0 else float("inf"))

        return result

    def compare_correlation_methods(
        self, sizes: list[int], sampling_rate: float = 44_100.0
    ) -> BenchmarkResult:
        """
        Compara el tiempo de ejecución de la correlación cruzada directa
        (O(N*M)) contra la correlación cruzada acelerada mediante FFT
        (O(N log N)) para señales de referencia y recibida de igual
        tamaño N.

        @param  sizes         Lista de tamaños N a evaluar.
        @param  sampling_rate Frecuencia de muestreo (Hz) usada para
                              instanciar el {@link EchoCorrelator}.
        @return                Objeto {@link BenchmarkResult} con los
                               tiempos promedio y el factor de
                               aceleración por tamaño.
        """
        correlator = EchoCorrelator(sampling_rate)
        result = BenchmarkResult()

        for n_samples in sizes:
            reference = self._rng.normal(size=n_samples)
            received = self._rng.normal(size=n_samples)

            direct_times = [
                self._time_callable(
                    lambda: correlator.correlate_direct(reference, received)
                )
                for _ in range(self._num_trials)
            ]
            fft_times = [
                self._time_callable(
                    lambda: correlator.correlate_fft(reference, received)
                )
                for _ in range(self._num_trials)
            ]

            avg_direct = float(np.mean(direct_times))
            avg_fft = float(np.mean(fft_times))

            result.sizes.append(n_samples)
            result.times_slow.append(avg_direct)
            result.times_fast.append(avg_fft)
            result.speedup.append(
                avg_direct / avg_fft if avg_fft > 0 else float("inf")
            )

        return result
