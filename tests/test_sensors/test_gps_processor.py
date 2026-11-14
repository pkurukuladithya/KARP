import unittest
from raspberry_pi.sensor_processing.gps_processor import GpsProcessor


class TestGpsProcessor(unittest.TestCase):
    def test_valid_gps_processing(self):
        proc = GpsProcessor()
        # Initial point
        state1 = proc.process(lat=37.7749, lon=-122.4194, speed_kmh=50.0, satellites=8, fix_quality=1)
        self.assertTrue(state1.is_valid)
        self.assertEqual(state1.satellites, 8)

        # Vehicle moves north (increase latitude)
        state2 = proc.process(lat=37.7755, lon=-122.4194, speed_kmh=52.0, satellites=9, fix_quality=1)
        self.assertTrue(state2.is_valid)
        # Heading northward should be near 0 degrees
        self.assertAlmostEqual(state2.heading_deg, 0.0, delta=10.0)

    def test_invalid_gps_fix(self):
        proc = GpsProcessor()
        state = proc.process(lat=0.0, lon=0.0, satellites=0, fix_quality=0, is_simulated=False)
        self.assertFalse(state.is_valid)


if __name__ == "__main__":
    unittest.main()
