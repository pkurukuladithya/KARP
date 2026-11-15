"""
Calibrated Monocular Distance Estimator.
Uses flat-road pinhole camera geometry and the vehicle ground contact point (bbox bottom).
Does NOT fabricate distances from bounding-box pixel sizes.
"""

from __future__ import annotations
import math
from typing import Optional, Tuple


class CalibratedMonocularDistanceEstimator:
    """
    Flat-road pinhole model. With the optical centre at cy and the camera pitched
    down by theta, a ground point imaged at row y is seen at depression angle
        phi = theta + atan((y - cy) / f)
    and its forward distance is Z = h_cam / tan(phi).

    focal_length_px is specified for `ref_width` pixels of image width and is
    scaled automatically to the actual frame width.
    """

    def __init__(
        self,
        camera_height_m: float = 1.25,
        camera_pitch_deg: float = 2.0,
        focal_length_px: float = 920.0,
        img_height: int = 720,
        ref_width: int = 1280,
    ):
        self.camera_height_m = camera_height_m
        self.camera_pitch_rad = math.radians(camera_pitch_deg)
        self.focal_length_px = focal_length_px
        self.img_height = img_height
        self.ref_width = ref_width

    def update_calibration(self, camera_height_m: float, camera_pitch_deg: float, focal_length_px: float) -> None:
        self.camera_height_m = camera_height_m
        self.camera_pitch_rad = math.radians(camera_pitch_deg)
        self.focal_length_px = focal_length_px

    def horizon_y(self, img_w: Optional[int] = None, img_h: Optional[int] = None) -> float:
        h = img_h or self.img_height
        w = img_w or int(h * 16 / 9)
        f = self.focal_length_px * (w / self.ref_width)
        return h / 2.0 - f * math.tan(self.camera_pitch_rad)

    def estimate_distance(
        self,
        bbox: Tuple[int, int, int, int],
        img_w: Optional[int] = None,
        img_h: Optional[int] = None,
    ) -> Optional[float]:
        """Distance in metres (1.5 .. 120), or None if the contact point is at/above the horizon."""
        h = img_h or self.img_height
        w = img_w or int(round(h * 16 / 9))
        f = self.focal_length_px * (w / self.ref_width)
        cy = h / 2.0

        y_bottom = float(bbox[3])
        phi = self.camera_pitch_rad + math.atan2(y_bottom - cy, f)

        # Require the contact point to be clearly below the horizon (~0.6 deg)
        if phi <= 0.01:
            return None

        distance_m = self.camera_height_m / math.tan(phi)
        return round(max(1.5, min(120.0, distance_m)), 1)

    @staticmethod
    def ttc_from_speed(distance_m: float, closing_speed_mps: float) -> Optional[float]:
        """TTC from a (smoothed) closing speed. None when not approaching meaningfully."""
        if closing_speed_mps > 0.5:
            return round(max(0.1, min(20.0, distance_m / closing_speed_mps)), 1)
        return None

    def compute_ttc(self, current_dist_m: float, prev_dist_m: float, dt_sec: float) -> Optional[float]:
        """TTC = current_dist / closing_speed (finite-difference form)."""
        if dt_sec <= 0.0 or prev_dist_m is None:
            return None
        closing_speed = (prev_dist_m - current_dist_m) / dt_sec
        return self.ttc_from_speed(current_dist_m, closing_speed)
