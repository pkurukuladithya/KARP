"""
Accelerometer Signal Processing & Dynamic Road Condition Vibration Filter.
Separates static Earth gravity (1.0g) and low-frequency chassis tilt from high-frequency road surface impacts.
"""

from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Tuple


@dataclass
class FilteredVibrationResult:
    raw_ax: float
    raw_ay: float
    raw_az: float
    raw_magnitude: float
    filtered_vibration: float  # High-frequency RMS vibration metric in g
    vibration_detected: bool
    active_threshold: float


class RoadConditionFilter:
    """
    Real-time high-pass filter and dynamic energy estimator.
    Uses exponential moving average high-pass filter:
        y[n] = alpha * (y[n-1] + x[n] - x[n-1])
    followed by rolling RMS computation over a short window (e.g., 100-200ms).
    """

    def __init__(
        self,
        sampling_hz: float = 20.0,
        cutoff_hz: float = 4.0,
        window_size: int = 10,
        initial_threshold_g: float = 2.20,
    ):
        self.sampling_hz = max(1.0, sampling_hz)
        self.cutoff_hz = cutoff_hz
        self.threshold_g = initial_threshold_g
        self.window_size = window_size

        # Compute filter coefficient alpha: alpha = RC / (RC + dt), where RC = 1 / (2 * pi * fc)
        dt = 1.0 / self.sampling_hz
        rc = 1.0 / (2.0 * math.pi * self.cutoff_hz)
        self.alpha = rc / (rc + dt)

        # Filter state
        self._prev_raw_mag = 1.0
        self._prev_filtered_mag = 0.0
        self._recent_squares: Deque[float] = deque(maxlen=window_size)

        # Baseline gravity compensation (auto-zero)
        self._gravity_est_z = 1.0

    def set_threshold(self, threshold_g: float) -> None:
        self.threshold_g = max(0.5, threshold_g)

    def process(self, ax: float, ay: float, az: float) -> FilteredVibrationResult:
        """Processes a single triaxial accelerometer sample."""
        # 1. Compute total vector magnitude: |a| = sqrt(ax^2 + ay^2 + az^2)
        raw_mag = math.sqrt(ax * ax + ay * ay + az * az)

        # 2. High-pass filter to remove DC component (gravity + steady cruise)
        filtered_mag = self.alpha * (self._prev_filtered_mag + raw_mag - self._prev_raw_mag)
        self._prev_raw_mag = raw_mag
        self._prev_filtered_mag = filtered_mag

        # 3. Accumulate squared dynamic deviation for RMS calculation
        self._recent_squares.append(filtered_mag * filtered_mag)
        rms_vibration = math.sqrt(sum(self._recent_squares) / len(self._recent_squares))

        # Peak impact magnitude: baseline 1.0g + dynamic vibration
        dynamic_peak = abs(raw_mag - 1.0)

        # Road vibration event triggered if RMS or peak exceeds configured threshold
        is_event = (raw_mag >= self.threshold_g) or (rms_vibration >= (self.threshold_g * 0.45))

        return FilteredVibrationResult(
            raw_ax=ax,
            raw_ay=ay,
            raw_az=az,
            raw_magnitude=raw_mag,
            filtered_vibration=rms_vibration,
            vibration_detected=is_event,
            active_threshold=self.threshold_g,
        )

    def reset(self) -> None:
        self._prev_raw_mag = 1.0
        self._prev_filtered_mag = 0.0
        self._recent_squares.clear()
