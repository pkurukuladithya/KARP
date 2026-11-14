"""
Traffic Light State Recognition Module.
Classifies state (RED, YELLOW, GREEN, UNKNOWN) using spatial vertical slot analysis and HSV color channels.
Guarantees uncertain signals are marked UNKNOWN rather than guessing.
"""

from __future__ import annotations
from typing import Optional, Tuple
import cv2
import numpy as np

from shared.protocols.message_schemas import TrafficLightData


class TrafficLightClassifier:
    def __init__(self, min_confidence: float = 0.70):
        self.min_confidence = min_confidence

    def classify_crop(self, crop_bgr: np.ndarray, bbox: Optional[Tuple[int, int, int, int]] = None) -> TrafficLightData:
        """Classifies the state of a cropped traffic light image."""
        if crop_bgr is None or crop_bgr.size == 0:
            return TrafficLightData(detected=False, state="UNKNOWN", confidence=0.0)

        h, w = crop_bgr.shape[:2]
        if h < 15 or w < 8:
            return TrafficLightData(detected=False, state="UNKNOWN", confidence=0.0)

        # Standard vertical traffic light:
        # Top 1/3: Red
        # Middle 1/3: Yellow
        # Bottom 1/3: Green
        slot_h = h // 3
        top_crop = crop_bgr[0:slot_h, :]
        mid_crop = crop_bgr[slot_h : 2 * slot_h, :]
        bot_crop = crop_bgr[2 * slot_h :, :]

        red_score = self._compute_color_energy(top_crop, color="red")
        yellow_score = self._compute_color_energy(mid_crop, color="yellow")
        green_score = self._compute_color_energy(bot_crop, color="green")

        scores = {"RED": red_score, "YELLOW": yellow_score, "GREEN": green_score}
        best_state = max(scores, key=scores.get)
        best_val = scores[best_state]

        # Require a clear dominant illumination to avoid false alarms
        if best_val > 15.0:
            # Normalize confidence between 0.70 and 0.98
            conf = min(0.98, 0.70 + (best_val / 100.0))
            return TrafficLightData(detected=True, state=best_state, confidence=round(conf, 2), bbox=bbox)
        else:
            return TrafficLightData(detected=True, state="UNKNOWN", confidence=0.30, bbox=bbox)

    def _compute_color_energy(self, patch_bgr: np.ndarray, color: str) -> float:
        if patch_bgr.size == 0:
            return 0.0

        hsv = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV)

        if color == "red":
            mask1 = cv2.inRange(hsv, np.array([0, 100, 120]), np.array([10, 255, 255]))
            mask2 = cv2.inRange(hsv, np.array([170, 100, 120]), np.array([180, 255, 255]))
            mask = cv2.bitwise_or(mask1, mask2)
        elif color == "yellow":
            mask = cv2.inRange(hsv, np.array([18, 90, 120]), np.array([35, 255, 255]))
        elif color == "green":
            mask = cv2.inRange(hsv, np.array([40, 80, 100]), np.array([90, 255, 255]))
        else:
            return 0.0

        # Mean intensity of matching illuminated pixels
        return float(np.mean(mask))
