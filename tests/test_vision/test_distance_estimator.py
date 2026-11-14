import unittest
from laptop_vision.object_detection.distance_estimator import CalibratedMonocularDistanceEstimator


class TestDistanceEstimator(unittest.TestCase):
    def setUp(self):
        self.estimator = CalibratedMonocularDistanceEstimator(
            camera_height_m=1.25,
            camera_pitch_deg=2.0,
            focal_length_px=920.0,
            img_height=720,
        )

    def test_forward_distance_estimation(self):
        # A vehicle whose tires touch the ground at y=550px (below horizon ~316px)
        bbox = (500, 380, 780, 550)
        dist = self.estimator.estimate_distance(bbox)

        self.assertIsNotNone(dist)
        # For typical 720p with 1.25m mount, contact at y=550 should be approx 4 - 8 meters
        self.assertGreater(dist, 2.0)
        self.assertLess(dist, 15.0)

    def test_horizon_cutoff(self):
        # Bounding box near/above horizon line (y <= 325)
        bbox = (500, 200, 600, 320)
        dist = self.estimator.estimate_distance(bbox)
        # Should return None for objects at or above vanishing horizon
        self.assertIsNone(dist)

    def test_ttc_calculation(self):
        # Vehicle closing from 20m to 15m in 0.5s -> closing speed 10 m/s -> TTC = 15 / 10 = 1.5s
        ttc = self.estimator.compute_ttc(current_dist_m=15.0, prev_dist_m=20.0, dt_sec=0.5)
        self.assertIsNotNone(ttc)
        self.assertAlmostEqual(ttc, 1.5, places=1)


if __name__ == "__main__":
    unittest.main()
