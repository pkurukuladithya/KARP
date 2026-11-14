"""
Lane Departure Warning (LDW) Logic.
Evaluates vehicle lateral displacement relative to lane center and triggers departure warnings.
"""

from typing import Tuple


class DepartureWarningEvaluator:
    def __init__(self, departure_threshold_m: float = 0.35):
        self.departure_threshold_m = departure_threshold_m

    def evaluate(self, vehicle_offset_m: float) -> Tuple[str, bool]:
        """
        Evaluates lane departure.
        Positive offset: Vehicle is to the RIGHT of lane center.
        Negative offset: Vehicle is to the LEFT of lane center.

        Returns (warning_status, is_departure):
            warning_status in ["NONE", "LEFT", "RIGHT"]
        """
        if vehicle_offset_m > self.departure_threshold_m:
            return "RIGHT", True
        elif vehicle_offset_m < -self.departure_threshold_m:
            return "LEFT", True
        else:
            return "NONE", False
