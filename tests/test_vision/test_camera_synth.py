import unittest
import numpy as np
from raspberry_pi.camera.camera_capture import CameraCaptureWorker


class TestCameraSynth(unittest.TestCase):
    def test_synthetic_frame_generation(self):
        worker = CameraCaptureWorker(width=640, height=360, fps=30, simulation_mode=True)
        frame = worker._render_synthetic_road_frame(1.5)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (360, 640, 3))
        self.assertEqual(frame.dtype, np.uint8)
        # Verify frame contains visual road content (non-zero)
        self.assertGreater(np.mean(frame), 5.0)


if __name__ == "__main__":
    unittest.main()
