"""
main.py

Punto de entrada único del taller: ejecuta secuencialmente la Parte 2
(experimentos con FFT) y la Parte 3 (experimentos de detección de ecos).

Uso:
    python main.py
"""

from __future__ import annotations

from main_parte2_fft import FftExperiment
from main_parte3_ecos import EchoDetectionExperiment


class TallerRunner:
    """
    Orquestador de alto nivel que ejecuta, en orden, todos los
    experimentos solicitados por el Taller de Proyecto Individual 1.
    """

    def __init__(self, sampling_rate: float = 44_100.0) -> None:
        """
        @param sampling_rate Frecuencia de muestreo (Hz) usada en todos
                             los experimentos, compartida entre las partes
                             2 y 3 para garantizar consistencia.
        """
        self._fft_experiment = FftExperiment(sampling_rate=sampling_rate)
        self._echo_experiment = EchoDetectionExperiment(sampling_rate=sampling_rate)

    def run_all(self) -> None:
        """
        Ejecuta, en orden, la Parte 2 y la Parte 3 del taller.
        """
        self._fft_experiment.run()
        self._echo_experiment.run()


if __name__ == "__main__":
    TallerRunner().run_all()
