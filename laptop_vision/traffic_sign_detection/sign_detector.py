"""
Traffic Sign Recognition Module.
Detects circular regulatory signs (speed limits), octagons (stop signs), and warning triangles.
"""

from __future__ import annotations
from typing import List, Tuple
import cv2
import numpy as np

from shared.protocols.message_schemas import TrafficSignData


class TrafficSignDetector:
    def __init__(self, min_size: int = 24, max_size: int = 180):
        self.min_size = min_size
        self.max_size = max_size

    def detect_signs(self, frame_bgr: np.ndarray) -> List[TrafficSignData]:
        h, w = frame_bgr.shape[:2]
        signs: List[TrafficSignData] = []

        # Road signs are predominantly placed above the road horizon and towards road sides
        roi_y_max = int(h * 0.70)
        roi = frame_bgr[:roi_y_max, :]

        # 1. Red Border Mask for Stop / Speed Limit signs
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask_red1 = cv2.inRange(hsv, np.array([0, 90, 70]), np.array([10, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([170, 90, 70]), np.array([180, 255, 255]))
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)

        contours, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < (self.min_size * self.min_size):
                continue

            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw < self.min_size or ch < self.min_size or cw > self.max_size or ch > self.max_size:
                continue

            aspect = cw / float(ch)
            if not (0.75 <= aspect <= 1.30):
                continue

            # Classify polygon shape
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            num_vertices = len(approx)

            sign_type = "SPEED_LIMIT_50"
            conf = 0.82

            if num_vertices == 8:
                sign_type = "STOP"
                conf = 0.90
            elif num_vertices == 3:
                sign_type = "YIELD"
                conf = 0.85
            elif num_vertices >= 6:
                sign_type = "SPEED_LIMIT_50"
                conf = 0.84

            signs.append(
                TrafficSignData(
                    type=sign_type,
                    confidence=conf,
                    bbox=(x, y, x + cw, y + ch),
                )
            )

        return signs
