"""
Regression tests for raw MJPEG buffer extraction (camera passthrough).

Some UVC drivers return the whole reused V4L2 buffer, so bytes from OLDER frames
follow the current frame's End-Of-Image marker. Extraction must return exactly the
current frame, and drop truncated frames instead of gluing stale data onto them.
"""

import unittest
import cv2
import numpy as np

from raspberry_pi.camera.camera_capture import CameraCaptureWorker


def _jpeg(value: int, w: int = 640, h: int = 360, noise: bool = False) -> bytes:
    img = np.full((h, w, 3), value, np.uint8)
    if noise:
        img = np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return buf.tobytes()


def _raw(buf: bytes) -> np.ndarray:
    return np.frombuffer(buf, np.uint8).reshape(1, -1)


class TestJpegExtraction(unittest.TestCase):
    def test_exact_frame(self):
        j = _jpeg(100)
        self.assertEqual(CameraCaptureWorker._extract_jpeg(_raw(j)), j)

    def test_stale_previous_frame_after_eoi_is_removed(self):
        old_big = _jpeg(0, noise=True)  # large earlier frame left in the buffer
        new_small = _jpeg(200)
        buffer = new_small + old_big[len(new_small):]  # driver reuses the buffer
        out = CameraCaptureWorker._extract_jpeg(_raw(buffer))
        self.assertEqual(out, new_small)
        self.assertLess(len(out), len(buffer))

    def test_truncated_frame_with_stale_tail_is_dropped(self):
        old_big = _jpeg(0, noise=True)
        new = _jpeg(50, noise=True)
        truncated = new[: len(new) // 2]  # frame cut short (USB error)
        buffer = truncated + old_big  # stale frame (with its own EOI) follows
        self.assertIsNone(CameraCaptureWorker._extract_jpeg(_raw(buffer)))

    def test_decoded_bgr_frame_is_not_treated_as_jpeg(self):
        self.assertIsNone(CameraCaptureWorker._extract_jpeg(np.zeros((8, 8, 3), np.uint8)))


if __name__ == "__main__":
    unittest.main()
