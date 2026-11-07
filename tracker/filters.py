"""One Euro low-pass filtering for noisy landmark coordinates.

Tuning: lower ``min_cutoff`` gives steadier output but adds lag; raise it to
follow small movements more closely. ``beta`` controls how much the cutoff
rises with movement speed, reducing lag during fast motion. A useful starting
point for normalized hand coordinates is ``min_cutoff=1.0, beta=0.02``.
"""

import math


class OneEuroFilter:
    """Adaptive low-pass filter for one scalar signal.

    Call ``filter(value, timestamp_seconds)`` once per sample. A separate
    instance should be used for each coordinate of a point.
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.02,
        derivative_cutoff: float = 1.0,
    ) -> None:
        if min_cutoff <= 0 or derivative_cutoff <= 0:
            raise ValueError("cutoff frequencies must be positive")
        if beta < 0:
            raise ValueError("beta must be non-negative")
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.derivative_cutoff = float(derivative_cutoff)
        self._timestamp: float | None = None
        self._value: float | None = None
        self._filtered_derivative = 0.0

    @staticmethod
    def _alpha(cutoff: float, elapsed: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / elapsed)

    def filter(self, value: float, timestamp: float) -> float:
        """Filter a scalar sample at ``timestamp`` (seconds)."""
        value = float(value)
        timestamp = float(timestamp)
        if self._timestamp is None:
            self._timestamp = timestamp
            self._value = value
            return value

        elapsed = timestamp - self._timestamp
        if elapsed <= 0:
            raise ValueError("timestamps must increase for each filter sample")

        previous_value = self._value
        assert previous_value is not None
        derivative = (value - previous_value) / elapsed
        derivative_alpha = self._alpha(self.derivative_cutoff, elapsed)
        self._filtered_derivative += derivative_alpha * (
            derivative - self._filtered_derivative
        )

        cutoff = self.min_cutoff + self.beta * abs(self._filtered_derivative)
        value_alpha = self._alpha(cutoff, elapsed)
        filtered_value = previous_value + value_alpha * (value - previous_value)

        self._timestamp = timestamp
        self._value = filtered_value
        return filtered_value

    def reset(self) -> None:
        """Clear filter history before starting a new signal track."""
        self._timestamp = None
        self._value = None
        self._filtered_derivative = 0.0
