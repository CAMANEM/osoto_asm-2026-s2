"""
signal_processing

Paquete con las herramientas núcleo de procesamiento digital de señales
del proyecto de radar acústico: transformadas de Fourier propias (DFT/FFT)
y correlación cruzada (directa y basada en FFT).
"""

from signal_processing.fourier_transform import FourierTransform
from signal_processing.correlator import EchoCorrelator, DelayEstimate

__all__ = ["FourierTransform", "EchoCorrelator", "DelayEstimate"]
