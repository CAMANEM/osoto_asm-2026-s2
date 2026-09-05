"""
signal_generator.py

Generación de señales acústicas sintéticas para los experimentos del
Taller de Proyecto Individual 1: pulsos, chirps, ecos simulados con
retardo y atenuación conocidos, y ruido aditivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class EchoDefinition:
    """
    Describe un eco sintético a partir de un retardo y una atenuación
    respecto de la señal transmitida original.

    @field delay_seconds Retardo del eco respecto a la señal transmitida,
                          en segundos.
    @field attenuation   Factor de atenuación de amplitud del eco, en el
                          rango (0, 1].
    """

    delay_seconds: float
    attenuation: float = 0.5


class AcousticSignalGenerator:
    """
    Genera señales acústicas de prueba (transmitida, eco(s) y ruido) para
    los experimentos de detección de ecos del sistema de radar acústico.

    La frecuencia de muestreo se fija en el constructor y se reutiliza en
    todos los métodos de generación, evitando inconsistencias entre
    señales generadas por la misma instancia.
    """

    def __init__(self, sampling_rate: float) -> None:
        """
        @param sampling_rate Frecuencia de muestreo en Hz (debe ser > 0).
        @throws ValueError si sampling_rate no es positiva.
        """
        if sampling_rate <= 0:
            raise ValueError("sampling_rate debe ser mayor que cero.")
        self._sampling_rate = sampling_rate

    @property
    def sampling_rate(self) -> float:
        """
        @return Frecuencia de muestreo configurada, en Hz.
        """
        return self._sampling_rate

    def time_vector(self, duration_seconds: float) -> np.ndarray:
        """
        Genera el vector de tiempo discreto correspondiente a una duración
        dada, a la frecuencia de muestreo configurada.

        @param  duration_seconds Duración de la señal en segundos.
        @return                   Arreglo de instantes de tiempo (s).
        """
        n_samples = int(round(duration_seconds * self._sampling_rate))
        return np.arange(n_samples) / self._sampling_rate

    def generate_pulse(
        self, duration_seconds: float, frequency_hz: float, amplitude: float = 1.0
    ) -> np.ndarray:
        """
        Genera un pulso senoidal de duración y frecuencia conocidas, el
        cual puede utilizarse como señal transmitida por el radar
        acústico.

        @param  duration_seconds Duración del pulso en segundos.
        @param  frequency_hz     Frecuencia de la senoidal en Hz.
        @param  amplitude        Amplitud pico de la señal (por defecto 1.0).
        @return                   Señal senoidal muestreada.
        """
        t = self.time_vector(duration_seconds)
        return amplitude * np.sin(2 * np.pi * frequency_hz * t)

    def generate_chirp(
        self,
        duration_seconds: float,
        start_freq_hz: float,
        end_freq_hz: float,
        amplitude: float = 1.0,
    ) -> np.ndarray:
        """
        Genera una señal tipo "chirp" lineal, cuya frecuencia instantánea
        varía linealmente entre `start_freq_hz` y `end_freq_hz` a lo largo
        de la duración indicada. Es una alternativa robusta al pulso
        senoidal simple como señal transmitida, ya que facilita su
        identificación posterior por correlación.

        @param  duration_seconds Duración del chirp en segundos.
        @param  start_freq_hz    Frecuencia inicial en Hz.
        @param  end_freq_hz      Frecuencia final en Hz.
        @param  amplitude        Amplitud pico de la señal.
        @return                   Señal chirp muestreada.
        """
        t = self.time_vector(duration_seconds)
        freq_slope = (end_freq_hz - start_freq_hz) / max(duration_seconds, 1e-12)
        instantaneous_phase = 2 * np.pi * (start_freq_hz * t + 0.5 * freq_slope * t**2)
        return amplitude * np.sin(instantaneous_phase)

    def apply_echo(
        self,
        transmitted_signal: np.ndarray,
        echo: EchoDefinition,
        total_duration_seconds: float,
    ) -> np.ndarray:
        """
        Ubica una copia atenuada y retardada (eco) de la señal transmitida
        dentro de un contenedor de silencio de duración total dada,
        simulando la reflexión de la señal en un objeto a cierta
        distancia.

        @param  transmitted_signal      Señal transmitida original.
        @param  echo                    Definición del eco
                                        ({@link EchoDefinition}) con su
                                        retardo y atenuación.
        @param  total_duration_seconds  Duración total del contenedor de
                                        salida (debe alcanzar para ubicar
                                        el eco completo).
        @return                          Señal con el eco ubicado en su
                                         posición temporal correspondiente.
        @throws ValueError si el eco no cabe dentro de la duración total.
        """
        n_total = int(round(total_duration_seconds * self._sampling_rate))
        delay_samples = int(round(echo.delay_seconds * self._sampling_rate))
        n_echo = transmitted_signal.shape[0]

        if delay_samples + n_echo > n_total:
            raise ValueError(
                "El eco no cabe dentro de la duración total especificada; "
                "aumente total_duration_seconds."
            )

        container = np.zeros(n_total, dtype=float)
        container[delay_samples : delay_samples + n_echo] += (
            echo.attenuation * transmitted_signal
        )
        return container

    def build_received_signal(
        self,
        transmitted_signal: np.ndarray,
        echoes: list[EchoDefinition],
        total_duration_seconds: float,
        noise_std: float = 0.0,
        random_seed: int | None = None,
    ) -> np.ndarray:
        """
        Construye una señal recibida sintética que combina uno o más ecos
        de la señal transmitida (cada uno con su propio retardo y
        atenuación) más ruido blanco gaussiano aditivo, emulando la señal
        que capturaría el micrófono/transductor del receptor.

        @param  transmitted_signal      Señal transmitida original.
        @param  echoes                  Lista de definiciones de eco
                                        ({@link EchoDefinition}).
        @param  total_duration_seconds  Duración total de la señal
                                        recibida, en segundos.
        @param  noise_std               Desviación estándar del ruido
                                        gaussiano aditivo (0 = sin ruido).
        @param  random_seed             Semilla opcional para
                                        reproducibilidad del ruido.
        @return                          Señal recibida sintética.
        """
        n_total = int(round(total_duration_seconds * self._sampling_rate))
        received = np.zeros(n_total, dtype=float)

        for echo in echoes:
            received += self.apply_echo(
                transmitted_signal, echo, total_duration_seconds
            )

        if noise_std > 0:
            rng = np.random.default_rng(random_seed)
            received += rng.normal(0.0, noise_std, size=n_total)

        return received
