"""
fourier_transform.py

Implementación propia (sin usar numpy.fft) de la Transformada Discreta de
Fourier (DFT) y la Transformada Rápida de Fourier (FFT, algoritmo
Cooley-Tukey radix-2), desarrolladas para el Taller de Proyecto Individual 1
(CE1110 - Análisis de Señales Mixtas).
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


class FourierTransform:
    """
    Clase utilitaria que agrupa las operaciones relacionadas con el análisis
    en el dominio de la frecuencia de una señal discreta: DFT directa (fuerza
    bruta), FFT recursiva (Cooley-Tukey) y utilidades derivadas (magnitud,
    fase, eje de frecuencias, relleno de ceros).

    Todos los métodos son estáticos porque la transformada no requiere
    mantener estado entre llamadas; se agrupan en una clase para mantener
    cohesión y un espacio de nombres claro dentro del paradigma OOP.
    """

    @staticmethod
    def dft(signal: Sequence[complex]) -> np.ndarray:
        """
        Calcula la Transformada Discreta de Fourier (DFT) de una señal
        mediante la definición directa (fuerza bruta), con complejidad
        O(N^2).

        X[k] = sum_{n=0}^{N-1} x[n] * exp(-j * 2 * pi * k * n / N)

        @param  signal Secuencia de N muestras (reales o complejas) en el
                        dominio del tiempo.
        @return         Arreglo numpy complejo de longitud N con la
                        representación en el dominio de la frecuencia.
        @throws ValueError si la señal está vacía.
        """
        x = np.asarray(signal, dtype=complex)
        n_samples = x.shape[0]

        if n_samples == 0:
            raise ValueError("La señal de entrada no puede estar vacía.")

        n_index = np.arange(n_samples)
        k_index = n_index.reshape((n_samples, 1))
        # Matriz de coeficientes exponenciales W_N^(k*n) de tamaño NxN.
        exponent_matrix = np.exp(-2j * np.pi * k_index * n_index / n_samples)

        return exponent_matrix @ x

    @classmethod
    def fft(cls, signal: Sequence[complex]) -> np.ndarray:
        """
        Calcula la Transformada Rápida de Fourier (FFT) utilizando el
        algoritmo recursivo de Cooley-Tukey (decimación en el tiempo,
        radix-2), con complejidad O(N log N).

        La longitud de la señal debe ser una potencia de 2. Si no lo es,
        se debe rellenar previamente con ceros usando
        {@link FourierTransform#zero_pad_to_power_of_two}.

        @param  signal Secuencia cuya longitud N es potencia de 2.
        @return         Arreglo numpy complejo de longitud N con el
                        espectro de la señal.
        @throws ValueError si la longitud de la señal no es potencia de 2
                            o si la señal está vacía.
        """
        x = np.asarray(signal, dtype=complex)
        n_samples = x.shape[0]

        if n_samples == 0:
            raise ValueError("La señal de entrada no puede estar vacía.")
        if not cls._is_power_of_two(n_samples):
            raise ValueError(
                "La longitud de la señal debe ser potencia de 2 para "
                "aplicar Cooley-Tukey; use zero_pad_to_power_of_two()."
            )

        return cls._fft_recursive(x)

    @classmethod
    def _fft_recursive(cls, x: np.ndarray) -> np.ndarray:
        """
        Paso recursivo interno del algoritmo Cooley-Tukey. Divide la señal
        en muestras pares e impares, calcula su FFT de forma recursiva y
        combina los resultados ("mariposa" / butterfly).

        @param  x Arreglo complejo de longitud potencia de 2.
        @return   Arreglo complejo con la FFT de x.
        """
        n_samples = x.shape[0]

        # Caso base de la recursión.
        if n_samples == 1:
            return x

        even = cls._fft_recursive(x[0::2])
        odd = cls._fft_recursive(x[1::2])

        factor = np.exp(-2j * np.pi * np.arange(n_samples // 2) / n_samples)
        twiddled_odd = factor * odd

        return np.concatenate([even + twiddled_odd, even - twiddled_odd])

    @classmethod
    def ifft(cls, spectrum: Sequence[complex]) -> np.ndarray:
        """
        Calcula la Transformada Inversa de Fourier (IFFT) reutilizando la
        FFT directa mediante la identidad:

            ifft(X) = conj(fft(conj(X))) / N

        Esto evita duplicar el algoritmo de mariposa y mantiene el
        principio DRY (Don't Repeat Yourself).

        @param  spectrum Espectro de longitud N (potencia de 2).
        @return           Señal reconstruida en el dominio del tiempo.
        """
        x = np.asarray(spectrum, dtype=complex)
        n_samples = x.shape[0]
        conjugated = np.conjugate(x)
        transformed = cls.fft(conjugated)
        return np.conjugate(transformed) / n_samples

    @staticmethod
    def _is_power_of_two(value: int) -> bool:
        """
        Determina si un entero positivo es potencia de 2.

        @param  value Entero a evaluar.
        @return        True si value = 2^k para algún k >= 0.
        """
        return value > 0 and (value & (value - 1)) == 0

    @staticmethod
    def next_power_of_two(value: int) -> int:
        """
        Calcula la siguiente potencia de 2 mayor o igual a un valor dado.

        @param  value Entero positivo de referencia.
        @return        Menor potencia de 2 tal que resultado >= value.
        """
        if value <= 1:
            return 1
        return 1 << math.ceil(math.log2(value))

    @classmethod
    def zero_pad_to_power_of_two(cls, signal: Sequence[complex]) -> np.ndarray:
        """
        Rellena una señal con ceros al final hasta alcanzar la siguiente
        potencia de 2, requisito para poder aplicar la FFT recursiva
        radix-2.

        @param  signal Señal de entrada de longitud arbitraria.
        @return         Señal rellenada con ceros, de longitud potencia de 2.
        """
        x = np.asarray(signal, dtype=complex)
        target_length = cls.next_power_of_two(x.shape[0])
        padded = np.zeros(target_length, dtype=complex)
        padded[: x.shape[0]] = x
        return padded

    @staticmethod
    def magnitude(spectrum: Sequence[complex]) -> np.ndarray:
        """
        Calcula la magnitud (módulo) de cada componente espectral.

        @param  spectrum Espectro complejo X[k].
        @return           Arreglo real con |X[k]|.
        """
        return np.abs(np.asarray(spectrum, dtype=complex))

    @staticmethod
    def phase(spectrum: Sequence[complex]) -> np.ndarray:
        """
        Calcula la fase (en radianes) de cada componente espectral.

        @param  spectrum Espectro complejo X[k].
        @return           Arreglo real con la fase de X[k] en radianes,
                          en el rango (-pi, pi].
        """
        return np.angle(np.asarray(spectrum, dtype=complex))

    @staticmethod
    def frequency_bins(n_samples: int, sampling_rate: float) -> np.ndarray:
        """
        Genera el eje de frecuencias (en Hz) asociado a un espectro de N
        muestras calculado a una frecuencia de muestreo dada.

        @param  n_samples      Número de muestras del espectro (N).
        @param  sampling_rate  Frecuencia de muestreo en Hz.
        @return                Arreglo de N frecuencias en Hz, donde la
                               segunda mitad corresponde a frecuencias
                               negativas (convención estándar de la DFT).
        """
        return np.fft.fftfreq(n_samples, d=1.0 / sampling_rate)
