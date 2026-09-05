"""
correlator.py

Implementación de correlación cruzada para la detección de ecos: una
versión directa (definición en el dominio del tiempo, O(N*M)) y una versión
acelerada mediante FFT (usando el teorema de convolución en frecuencia,
O(N log N)).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from signal_processing.fourier_transform import FourierTransform


@dataclass(frozen=True)
class DelayEstimate:
    """
    Objeto de valor (value object) que encapsula el resultado de una
    estimación de retardo entre dos señales.

    @field lag_samples   Retardo estimado en número de muestras.
    @field lag_seconds   Retardo estimado en segundos.
    @field peak_value    Valor de correlación en el pico detectado.
    @field correlation   Arreglo completo de correlación cruzada.
    @field lags          Arreglo de retardos (en muestras) asociado a
                          `correlation`, con la misma longitud.
    """

    lag_samples: int
    lag_seconds: float
    peak_value: float
    correlation: np.ndarray
    lags: np.ndarray


class EchoCorrelator:
    """
    Encapsula las técnicas de correlación cruzada utilizadas para detectar,
    dentro de una señal recibida (contaminada con ruido y reflexiones), el
    retardo asociado a un eco de una señal transmitida conocida.

    La clase mantiene la frecuencia de muestreo como estado, ya que es
    necesaria para convertir el retardo estimado (en muestras) a segundos.
    """

    def __init__(self, sampling_rate: float) -> None:
        """
        Construye un correlador para una frecuencia de muestreo dada.

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

    def correlate_direct(
        self, reference: Sequence[float], received: Sequence[float]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Calcula la correlación cruzada completa entre dos señales mediante
        la definición directa en el dominio del tiempo (fuerza bruta),
        con complejidad O(N * M).

            r[l] = sum_n reference[n] * received[n + l]

        Con esta convención, si `received` contiene una copia de
        `reference` retardada `d` muestras (eco tardío), el pico de la
        correlación aparece en el lag positivo l = d, consistente con un
        tiempo de vuelo positivo.

        @param  reference Señal transmitida conocida, de longitud N.
        @param  received  Señal recibida (con eco/ruido), de longitud M.
        @return            Tupla (lags, correlation) donde `lags` son los
                           retardos en muestras (de -(M-1) a N-1) y
                           `correlation` son los valores de correlación
                           cruzada asociados.
        """
        ref = np.asarray(reference, dtype=float)
        rec = np.asarray(received, dtype=float)
        n_ref, n_rec = ref.shape[0], rec.shape[0]

        total_lags = n_ref + n_rec - 1
        correlation = np.zeros(total_lags, dtype=float)

        # Correlación cruzada completa: el lag l = n_rec_index - n_ref_index
        # debe recorrer desde -(n_ref - 1) (cuando `received` empieza mucho
        # antes que `reference`) hasta n_rec - 1 (cuando el eco aparece casi
        # al final de `received`).
        for idx, lag in enumerate(range(-(n_ref - 1), n_rec)):
            acc = 0.0
            for n in range(n_ref):
                m = n + lag
                if 0 <= m < n_rec:
                    acc += ref[n] * rec[m]
            correlation[idx] = acc

        lags = np.arange(-(n_ref - 1), n_rec)
        return lags, correlation

    def correlate_fft(
        self, reference: Sequence[float], received: Sequence[float]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Calcula la correlación cruzada completa entre dos señales
        utilizando la FFT propia ({@link FourierTransform}) y el teorema
        de convolución: la correlación en el tiempo equivale al producto
        en frecuencia de la FFT de una señal por el conjugado de la FFT de
        la otra, seguido de la IFFT.

            r = IFFT( conj(FFT(reference_padded)) * FFT(received_padded) )

        Esta combinación (conjugado de la referencia, sin conjugar la
        señal recibida) es la que reproduce, en el dominio circular, la
        misma convención de signo que {@link #correlate_direct}: un eco
        tardío en `received` produce un pico en un lag positivo.

        Complejidad O(N log N), sensiblemente menor que la versión directa
        para señales largas.

        @param  reference Señal transmitida conocida, de longitud N.
        @param  received  Señal recibida (con eco/ruido), de longitud M.
        @return            Tupla (lags, correlation) equivalente en
                           contenido a la retornada por
                           {@link #correlate_direct}.
        """
        ref = np.asarray(reference, dtype=float)
        rec = np.asarray(received, dtype=float)
        n_ref, n_rec = ref.shape[0], rec.shape[0]
        total_lags = n_ref + n_rec - 1

        fft_length = FourierTransform.next_power_of_two(total_lags)

        ref_padded = np.zeros(fft_length, dtype=complex)
        ref_padded[:n_ref] = ref
        rec_padded = np.zeros(fft_length, dtype=complex)
        rec_padded[:n_rec] = rec

        ref_spectrum = FourierTransform.fft(ref_padded)
        rec_spectrum = FourierTransform.fft(rec_padded)

        cross_spectrum = np.conjugate(ref_spectrum) * rec_spectrum
        raw_correlation = FourierTransform.ifft(cross_spectrum).real

        # Reordenar la salida circular de la FFT para que corresponda a
        # retardos negativos y positivos, igual que en correlate_direct.
        correlation = np.concatenate(
            [raw_correlation[-(n_ref - 1):], raw_correlation[:n_rec]]
        )
        lags = np.arange(-(n_ref - 1), n_rec)
        return lags, correlation

    def estimate_delay(
        self, lags: np.ndarray, correlation: np.ndarray
    ) -> DelayEstimate:
        """
        Estima el retardo (tiempo de vuelo) entre la señal transmitida y
        el eco recibido, ubicando el máximo absoluto de la función de
        correlación cruzada.

        @param  lags        Arreglo de retardos en muestras.
        @param  correlation Arreglo de valores de correlación cruzada
                            asociado a `lags`.
        @return              Objeto {@link DelayEstimate} con el retardo en
                             muestras y segundos, y el valor de pico.
        """
        peak_index = int(np.argmax(np.abs(correlation)))
        lag_samples = int(lags[peak_index])
        lag_seconds = lag_samples / self._sampling_rate
        peak_value = float(correlation[peak_index])

        return DelayEstimate(
            lag_samples=lag_samples,
            lag_seconds=lag_seconds,
            peak_value=peak_value,
            correlation=correlation,
            lags=lags,
        )
