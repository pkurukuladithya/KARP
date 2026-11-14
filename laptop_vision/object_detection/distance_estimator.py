"""
Calibrated Monocular Distance Estimator.
Uses flat-earth pinhole camera geometry, horizon vanishing line, and vehicle ground contact points.
Does NOT fabricate arbitrary distances from bounding-box pixel sizes.
"""

from __future__ import annotations
import math
from typing import Optional, Tuple


class CalibratedMonocularDistanceEstimator:
    """
    Computes approximate forward distance to detected road objects using camera pitch and mounting height:
        Z ≈ h_cam / tan(theta_pitch + arctan((y_bottom - y_horizon) / f_y))
    """

    def __init__(
        self,
        camera_height_m: float = 1.25,
        camera_pitch_deg: float = 2.0,
        focal_length_px: float = 920.0,
        img_height: int = 720,
    ):
        self.camera_height_m = camera_height_m
        self.camera_pitch_rad = math.radians(camera_pitch_deg)
        self.focal_length_px = focal_length_px
        self.img_height = img_height
        self.horizon_y = img_height * 0.44

    def update_calibration(self, camera_height_m: float, camera_pitch_deg: float, focal_length_px: float) -> None:
        self.camera_height_m = camera_height_m
        self.camera_pitch_rad = math.radians(camera_pitch_deg)
        self.focal_length_px = focal_length_px

    def estimate_distance(self, bbox: Tuple[int, int, int, int]) -> Optional[float]:
        """
        Given bbox (xmin, ymin, xmax, ymax), calculates physical distance in meters.
        Returns distance rounded to 1 decimal place, or None if target is above the road horizon.
        """
        xmin, ymin, xmax, ymax = bbox
        y_bottom = float(ymax)

        # Ground contact point must be below the horizon line
        dy = y_bottom - self.horizon_y
        if dy <= 10.0:
            # Object is too far / near or above horizon, distance estimation invalid
            return None

        # Angle from optical axis to ground contact point
        alpha = math.atan2(dy, self.focal_length_px)
        total_angle = self.camera_pitch_rad + alpha

        if total_angle <= 0.01:
            return None

        distance_m = self.camera_height_m / math.tan(total_angle)

        # Plausible range for forward ADAS camera: 1.5m to 120m
        if 1.5 <= distance_m <= 120.0:
            return round(distance_m, 1)
        elif distance_m > 120.0:
            return 120.0
        return 1.5

    def compute_ttc(self, current_dist_m: float, prev_dist_m: float, dt_sec: float) -> Optional[float]:
        """
        Calculates Time-To-Collision (TTC) in seconds:
            TTC = current_dist / closing_speed
        """
        if dt_sec <= 0.0 or prev_dist_m is None:
            return None

        closing_speed = (prev_dist_m - current_dist_m) / dt_sec  # m/s (positive when approaching)
        if closing_speed > 0.5:  # Closing at more than 1.8 km/h
            ttc = current_dist_m / closing_speed
            return round(max(0.1, min(20.0, ttc)), 1)
        return None
