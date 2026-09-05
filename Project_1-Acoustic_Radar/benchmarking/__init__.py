"""
benchmarking

Paquete con las utilidades de medición y comparación de desempeño entre
implementaciones directas y aceleradas (FFT) de transformada y correlación.
"""

from benchmarking.benchmark import PerformanceBenchmark, BenchmarkResult

__all__ = ["PerformanceBenchmark", "BenchmarkResult"]
