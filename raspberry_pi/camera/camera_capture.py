"""
Camera Acquisition Worker for Raspberry Pi.
Captures USB video stream from /dev/video0 or renders dynamic synthetic road video in simulation mode.
"""

from __future__ import annotations
import math
import time
from typing import Optional, Tuple
from PySide6.QtCore import QThread, Signal
import cv2
import numpy as np


class CameraCaptureWorker(QThread):
    frame_captured = Signal(np.ndarray, int, int)  # (frame_bgr, frame_id, timestamp_ms)
    camera_status_changed = Signal(bool, str)

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        simulation_mode: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = max(1, fps)
        self.simulation_mode = simulation_mode
        self._running = True
        self._frame_id = 0

    def stop(self) -> None:
        self._running = False
        self.wait(1000)

    def run(self) -> None:
        cap: Optional[cv2.VideoCapture] = None
        use_sim = self.simulation_mode

        if not use_sim:
            cap = cv2.VideoCapture(self.camera_index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                cap.set(cv2.CAP_PROP_FPS, self.fps)
                self.camera_status_changed.emit(True, f"Hardware Camera #{self.camera_index} Opened")
            else:
                self.camera_status_changed.emit(False, f"Camera #{self.camera_index} unavailable. Switching to Simulation Mode.")
                use_sim = True
                if cap:
                    cap.release()
                    cap = None
        else:
            self.camera_status_changed.emit(True, "Synthetic Camera Generator Active")

        target_interval = 1.0 / self.fps
        t_sim = 0.0

        while self._running:
            start_time = time.time()
            self._frame_id += 1
            ts_ms = int(time.time() * 1000)

            frame: Optional[np.ndarray] = None

            if not use_sim and cap is not None and cap.isOpened():
                ret, raw_frame = cap.read()
                if ret and raw_frame is not None:
                    if raw_frame.shape[1] != self.width or raw_frame.shape[0] != self.height:
                        frame = cv2.resize(raw_frame, (self.width, self.height))
                    else:
                        frame = raw_frame
                else:
                    use_sim = True
                    self.camera_status_changed.emit(False, "Camera frame read failed. Falling back to simulation.")

            if use_sim or frame is None:
                t_sim += target_interval
                frame = self._render_synthetic_road_frame(t_sim)

            self.frame_captured.emit(frame, self._frame_id, ts_ms)

            elapsed = time.time() - start_time
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        if cap and cap.isOpened():
            cap.release()
        self.camera_status_changed.emit(False, "Camera Closed")

    def _render_synthetic_road_frame(self, t: float) -> np.ndarray:
        """Renders an asphalt road with lane markings and moving vehicle targets."""
        w, h = self.width, self.height
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Sky Gradient (deep navy dusk to amber horizon)
        horizon_y = int(h * 0.44)
        cv2.rectangle(frame, (0, 0), (w, horizon_y), (45, 30, 20), -1)

        # Ground / Grass Verge
        cv2.rectangle(frame, (0, horizon_y), (w, h), (30, 45, 35), -1)

        # Road Asphalt Polygon
        vanish_x = int(w * 0.5 + 40.0 * math.sin(t * 0.2))  # Gentle road curve
        vanish_y = horizon_y
        road_pts = np.array([
            [int(w * 0.05), h],
            [vanish_x - 30, vanish_y],
            [vanish_x + 30, vanish_y],
            [int(w * 0.95), h],
        ], dtype=np.int32)
        cv2.fillPoly(frame, [road_pts], (40, 40, 40))

        # Lane Markings
        # Left boundary (Solid White)
        cv2.line(frame, (int(w * 0.15), h), (vanish_x - 20, vanish_y), (220, 220, 220), 4)
        # Right boundary (Solid Yellow)
        cv2.line(frame, (int(w * 0.85), h), (vanish_x + 20, vanish_y), (0, 215, 255), 4)

        # Center dashed line (Animated moving towards camera)
        offset = (t * 8.0) % 1.0
        num_segments = 7
        for i in range(num_segments):
            y_norm1 = ((i + offset) / num_segments) ** 2
            y_norm2 = ((i + offset + 0.5) / num_segments) ** 2
            if y_norm2 > 1.0:
                continue
            y1 = int(vanish_y + (h - vanish_y) * y_norm1)
            y2 = int(vanish_y + (h - vanish_y) * y_norm2)
            cx1 = int(vanish_x + (w * 0.5 - vanish_x) * (y_norm1 ** 0.5))
            cx2 = int(vanish_x + (w * 0.5 - vanish_x) * (y_norm2 ** 0.5))
            cv2.line(frame, (cx1, y1), (cx2, y2), (240, 240, 240), max(2, int(6 * y_norm2)))

        # Synthetic Lead Vehicle ahead
        lead_dist_norm = 0.55 + 0.15 * math.sin(t * 0.3)
        car_y = int(vanish_y + (h - vanish_y) * lead_dist_norm)
        car_scale = lead_dist_norm * 1.4
        car_w = int(120 * car_scale)
        car_h = int(70 * car_scale)
        car_x = int(vanish_x + (w * 0.52 - vanish_x) * (lead_dist_norm ** 0.5) - car_w // 2)

        # Draw vehicle body (Red SUV)
        cv2.rectangle(frame, (car_x, car_y - car_h), (car_x + car_w, car_y), (30, 30, 180), -1)
        # Vehicle roof
        cv2.rectangle(frame, (car_x + int(car_w * 0.15), car_y - car_h - int(car_h * 0.4)), (car_x + int(car_w * 0.85), car_y - car_h), (40, 40, 200), -1)
        # Tail lights
        cv2.rectangle(frame, (car_x + 5, car_y - int(car_h * 0.7)), (car_x + int(car_w * 0.25), car_y - int(car_h * 0.4)), (20, 20, 240), -1)
        cv2.rectangle(frame, (car_x + car_w - int(car_w * 0.25), car_y - int(car_h * 0.7)), (car_x + car_w - 5, car_y - int(car_h * 0.4)), (20, 20, 240), -1)

        # Simulation watermark
        cv2.putText(frame, "[SYNTHETIC ROAD CAMERA FEED]", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 210, 255), 2)

        return frame
