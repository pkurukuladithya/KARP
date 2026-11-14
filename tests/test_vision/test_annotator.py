import unittest
import numpy as np
from laptop_vision.visual_annotator.annotator import VisualAnnotator
from shared.protocols.message_schemas import (
    LaneData,
    DetectedObject,
    TrafficLightData,
    TrafficSignData,
    WarningAlert,
)


class TestVisualAnnotator(unittest.TestCase):
    def test_annotation_rendering(self):
        annotator = VisualAnnotator()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        lanes = LaneData(
            detected=True,
            departure_warning="NONE",
            vehicle_offset_m=0.05,
            curvature_m=800.0,
            left_lane_pts=[(300, 700), (450, 500), (550, 380)],
            right_lane_pts=[(980, 700), (830, 500), (730, 380)],
        )
        objects = [
            DetectedObject(id=1, class_name="car", confidence=0.88, bbox=(550, 400, 720, 530), estimated_distance_m=18.0)
        ]
        tl = TrafficLightData(detected=True, state="GREEN", confidence=0.95)
        signs = [TrafficSignData(type="SPEED_LIMIT_50", confidence=0.84, bbox=(1050, 80, 1120, 150))]
        warnings = [WarningAlert(code="ALL_OK", level="INFO", message="Normal Driving")]

        annotated = annotator.annotate_frame(
            frame_bgr=frame,
            lanes=lanes,
            objects=objects,
            traffic_light=tl,
            traffic_signs=signs,
            warnings=warnings,
            fps=32.5,
            latency_ms=18.2,
            device_name="NVIDIA RTX 4050 (CUDA)",
        )

        self.assertIsNotNone(annotated)
        self.assertEqual(annotated.shape, (720, 1280, 3))
        self.assertGreater(np.mean(annotated), 0.5)


if __name__ == "__main__":
    unittest.main()
