import unittest
from raspberry_pi.sensor_processing.accelerometer_filter import RoadConditionFilter


class TestAccelerometerFilter(unittest.TestCase):
    def test_static_gravity_removal(self):
        # 1.0g static gravity on Z axis during smooth highway driving
        filter_inst = RoadConditionFilter(sampling_hz=20.0, cutoff_hz=4.0, initial_threshold_g=2.2)

        # Feed 30 samples of stationary/steady 1.0g
        res = None
        for _ in range(30):
            res = filter_inst.process(ax=0.0, ay=0.0, az=1.0)

        self.assertIsNotNone(res)
        self.assertAlmostEqual(res.raw_magnitude, 1.0, places=2)
        # High pass filter dynamic RMS should converge close to 0.0g
        self.assertLess(res.filtered_vibration, 0.15)
        self.assertFalse(res.vibration_detected)

    def test_pothole_impact_detection(self):
        filter_inst = RoadConditionFilter(sampling_hz=20.0, cutoff_hz=4.0, initial_threshold_g=2.2)

        # Warm up baseline
        for _ in range(15):
            filter_inst.process(0.0, 0.0, 1.0)

        # Severe road impact: 2.8g spike on Z and lateral shock
        res = filter_inst.process(ax=0.5, ay=-0.4, az=2.8)
        self.assertGreaterEqual(res.raw_magnitude, 2.8)
        self.assertTrue(res.vibration_detected)

    def test_dynamic_threshold_update(self):
        filter_inst = RoadConditionFilter(initial_threshold_g=2.2)
        filter_inst.set_threshold(3.0)
        self.assertEqual(filter_inst.threshold_g, 3.0)

        res = filter_inst.process(0.0, 0.0, 2.5)
        # 2.5g is below 3.0g threshold, so not detected
        self.assertFalse(res.vibration_detected)


if __name__ == "__main__":
    unittest.main()
