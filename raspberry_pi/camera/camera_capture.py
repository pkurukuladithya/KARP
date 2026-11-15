"""
Camera Acquisition Worker for Raspberry Pi.
Captures the USB camera (V4L2 + MJPG, 1-frame buffer for low latency) or renders a
synthetic road in simulation mode.

Frames are delivered to "sinks" (e.g. the network sender) directly from this
thread, so video never waits on the GUI event loop. A throttled, pre-converted
QImage preview is emitted only while the laptop AI stream is unavailable.
"""

from __future__ import annotations
import logging
import math
import sys
import time
from typing import Callable, List, Optional, Tuple
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import cv2
import numpy as np

logger = logging.getLogger("KARP.Camera")

FrameSink = Callable[[np.ndarray, int, int], None]


def bgr_to_qimage(frame_bgr: np.ndarray) -> QImage:
    """BGR ndarray -> QImage in Format_RGB32 (the fastest format for QPainter to draw)."""
    bgra = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2BGRA)
    h, w = bgra.shape[:2]
    return QImage(bgra.data, w, h, 4 * w, QImage.Format_RGB32).copy()


class CameraCaptureWorker(QThread):
    frame_captured = Signal(np.ndarray, int, int)  # kept for compatibility (not used by the HMI)
    preview_ready = Signal(QImage, float)  # (qimage, capture_fps) - local raw preview
    camera_status_changed = Signal(bool, str)

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        simulation_mode: bool = False,
        stream_width: Optional[int] = None,
        stream_height: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = max(1, fps)
        self.simulation_mode = simulation_mode
        # Output size sent to the laptop / preview. Defaults to capture size.
        self.out_w = stream_width or width
        self.out_h = stream_height or height
        self._running = True
        self._frame_id = 0
        self._sinks: List[FrameSink] = []
        self.preview_enabled = True
        self.preview_max_fps = 15.0
        self._last_preview = 0.0
        self._capture_fps = 0.0

    def add_frame_sink(self, sink: FrameSink) -> None:
        """Registers a callable invoked from the camera thread for every frame."""
        self._sinks.append(sink)

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    # ------------------------------------------------------------------ camera
    def _open_camera(self) -> Optional[cv2.VideoCapture]:
        if sys.platform.startswith("linux"):
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            cap.release()
            return None
        # MJPG must be requested BEFORE the resolution. Raw YUYV at 720p is limited
        # to ~7-10 fps by USB 2.0 bandwidth on most webcams -> laggy video.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always deliver the newest frame

        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4))
        logger.info(
            f"Camera #{self.camera_index} opened: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
            f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps, format {fourcc_str!r}"
        )
        return cap

    def _deliver(self, frame: np.ndarray) -> None:
        if frame.shape[1] != self.out_w or frame.shape[0] != self.out_h:
            frame = cv2.resize(frame, (self.out_w, self.out_h), interpolation=cv2.INTER_AREA)
        self._frame_id += 1
        ts_ms = int(time.time() * 1000)

        for sink in self._sinks:
            try:
                sink(frame, self._frame_id, ts_ms)
            except Exception as e:
                logger.debug(f"Frame sink error: {e}")

        now = time.time()
        if self.preview_enabled and now - self._last_preview >= 1.0 / self.preview_max_fps:
            self._last_preview = now
            self.preview_ready.emit(bgr_to_qimage(frame), self._capture_fps)

    def run(self) -> None:
        cap: Optional[cv2.VideoCapture] = None
        target_interval = 1.0 / self.fps
        t_sim = 0.0
        frame_count = 0
        last_fps_time = time.time()

        while self._running:
            loop_start = time.time()
            if not self.simulation_mode:
                if cap is None:
                    cap = self._open_camera()
                    if cap is None:
                        self.camera_status_changed.emit(False, f"Camera #{self.camera_index} Not Connected")
                        time.sleep(1.0)
                        continue
                    self.camera_status_changed.emit(True, f"Camera #{self.camera_index} Opened")

                ret, frame = cap.read()
                if not ret or frame is None:
                    self.camera_status_changed.emit(False, "Camera frame read failed. Reconnecting...")
                    cap.release()
                    cap = None
                    time.sleep(0.5)
                    continue
                self._deliver(frame)
            else:
                t_sim += target_interval
                self._deliver(self._render_synthetic_road_frame(t_sim))
                sleep_time = target_interval - (time.time() - loop_start)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            frame_count += 1
            now = time.time()
            if now - last_fps_time >= 1.0:
                self._capture_fps = frame_count / (now - last_fps_time)
                frame_count = 0
                last_fps_time = now

        if cap is not None:
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
