"""
generation

Paquete con las herramientas de generación de señales acústicas sintéticas
(pulsos, chirps, ecos y ruido) para los experimentos del proyecto.
"""

from generation.signal_generator import AcousticSignalGenerator, EchoDefinition

__all__ = ["AcousticSignalGenerator", "EchoDefinition"]
