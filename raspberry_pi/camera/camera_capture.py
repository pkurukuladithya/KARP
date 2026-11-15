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
        passthrough: bool = True,
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
        # Forward the camera's own MJPEG frames untouched (no decode/resize/encode on the Pi)
        self.passthrough = passthrough
        self._passthrough_active = False
        self._jpeg_bytes_avg = 0.0

    def add_frame_sink(self, sink: FrameSink) -> None:
        """Registers a callable invoked from the camera thread for every frame."""
        self._sinks.append(sink)

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    # ------------------------------------------------------------------ camera
    def _open_camera(self, passthrough: bool) -> Optional[cv2.VideoCapture]:
        # Passthrough: ask the camera directly for the stream size (it picks the nearest
        # mode it supports; the laptop accepts any size). Otherwise capture, then resize.
        req_w, req_h = (self.out_w, self.out_h) if passthrough else (self.width, self.height)
        if sys.platform.startswith("linux"):
            self._disable_exposure_priority()
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            cap.release()
            return None
        # MJPG must be requested BEFORE the resolution. Raw YUYV at 720p is limited
        # to ~7-10 fps by USB 2.0 bandwidth on most webcams -> laggy video.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_h)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always deliver the newest frame
        if passthrough:
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)  # V4L2: return the raw MJPEG buffer

        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4))
        logger.info(
            f"Camera #{self.camera_index} opened: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
            f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps, format {fourcc_str!r}, "
            f"passthrough={'requested' if passthrough else 'off'}"
        )
        return cap

    def _disable_exposure_priority(self) -> None:
        """
        In dim light most UVC webcams lower their frame rate (to 5-15 fps) to get longer
        exposure ("exposure priority"). For ADAS we want a constant frame rate instead.
        Control names differ between kernels, so try both; failures are harmless.
        """
        import subprocess
        dev = f"/dev/video{self.camera_index}"
        for ctrl in ("exposure_dynamic_framerate=0", "exposure_auto_priority=0"):
            try:
                subprocess.run(["v4l2-ctl", "-d", dev, "-c", ctrl], capture_output=True, timeout=2)
            except Exception:
                pass

    @staticmethod
    def _extract_jpeg(frame: Optional[np.ndarray]) -> Optional[bytes]:
        """Returns JPEG bytes if `frame` is a raw MJPEG buffer (CONVERT_RGB=0), else None."""
        if frame is None or (frame.ndim == 3 and frame.shape[2] == 3):
            return None
        data = frame.reshape(-1)
        n = data.size
        if n < 4 or data[0] != 0xFF or data[1] != 0xD8:
            return None

        # Some UVC drivers hand over the whole (reused) V4L2 buffer: after this frame's
        # End-Of-Image there are stale bytes from OLDER frames. Searching for the *last*
        # EOI therefore glues old image data onto the new frame (torn picture, ~1 MB/frame).
        # Parse properly instead: walk header segments to Start-Of-Scan, then the first
        # real marker in the entropy-coded data must be EOI (0xFF is only ever followed by
        # 0x00 stuffing or RST0-7 inside scan data). Anything else = truncated -> drop.
        i = 2
        while True:
            if i + 4 > n or data[i] != 0xFF:
                return None
            marker = int(data[i + 1])
            if marker == 0xFF:  # fill byte
                i += 1
                continue
            seg_len = (int(data[i + 2]) << 8) | int(data[i + 3])
            if marker == 0xDA:  # Start Of Scan
                scan_start = i + 2 + seg_len
                break
            i += 2 + seg_len

        if scan_start >= n - 1:
            return None
        ff_pos = np.flatnonzero(data[scan_start : n - 1] == 0xFF) + scan_start
        if ff_pos.size == 0:
            return None
        nxt = data[ff_pos + 1]
        is_marker = (nxt != 0x00) & (nxt != 0xFF) & ((nxt < 0xD0) | (nxt > 0xD7))
        markers = ff_pos[is_marker]
        if markers.size == 0 or data[markers[0] + 1] != 0xD9:
            return None  # incomplete frame followed by stale data
        end = int(markers[0]) + 2
        return data[:end].tobytes()

    def _deliver_jpeg(self, jpeg: bytes) -> None:
        self._frame_id += 1
        ts_ms = int(time.time() * 1000)
        self._jpeg_bytes_avg = 0.95 * self._jpeg_bytes_avg + 0.05 * len(jpeg) if self._jpeg_bytes_avg else len(jpeg)
        for sink in self._sinks:
            try:
                sink(jpeg, self._frame_id, ts_ms)
            except Exception as e:
                logger.debug(f"Frame sink error: {e}")

        now = time.time()
        if self.preview_enabled and now - self._last_preview >= 1.0 / self.preview_max_fps:
            self._last_preview = now
            # Half-resolution decode is ~4x cheaper and plenty for the local fallback preview
            bgr = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_REDUCED_COLOR_2)
            if bgr is not None:
                self.preview_ready.emit(bgr_to_qimage(bgr), self._capture_fps)

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
        validated = True
        pt_failures = 0
        target_interval = 1.0 / self.fps
        t_sim = 0.0
        frame_count = 0
        last_fps_time = time.time()

        while self._running:
            loop_start = time.time()
            if not self.simulation_mode:
                if cap is None:
                    want_pt = self.passthrough and sys.platform.startswith("linux")
                    cap = self._open_camera(want_pt)
                    if cap is None:
                        self.camera_status_changed.emit(False, f"Camera #{self.camera_index} Not Connected")
                        time.sleep(1.0)
                        continue
                    self._passthrough_active = want_pt
                    validated = not want_pt
                    pt_failures = 0
                    self.camera_status_changed.emit(True, f"Camera #{self.camera_index} Opened")

                ret, frame = cap.read()
                if not ret or frame is None:
                    self.camera_status_changed.emit(False, "Camera frame read failed. Reconnecting...")
                    cap.release()
                    cap = None
                    time.sleep(0.5)
                    continue

                is_bgr = frame.ndim == 3 and frame.shape[2] == 3
                jpeg = self._extract_jpeg(frame) if (self._passthrough_active and not is_bgr) else None

                if self._passthrough_active and not is_bgr:
                    test = None
                    if jpeg is not None and not validated:
                        test = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_REDUCED_COLOR_2)
                        if test is None:
                            jpeg = None
                    if jpeg is None:
                        pt_failures += 1
                        if pt_failures >= 15:
                            logger.warning(
                                "Camera MJPEG passthrough produced 15 unusable frames in a row on this "
                                "camera/driver; switching to decode+encode path"
                            )
                            self.passthrough = False
                            cap.release()
                            cap = None
                        continue  # drop this (truncated/corrupt) frame
                    pt_failures = 0
                    if not validated:
                        validated = True
                        logger.info(
                            f"MJPEG passthrough ACTIVE: {test.shape[1] * 2}x{test.shape[0] * 2} camera JPEGs "
                            f"forwarded without re-encoding ({len(jpeg) / 1024:.0f} KB/frame)"
                        )

                if jpeg is not None:
                    self._deliver_jpeg(jpeg)
                elif is_bgr:
                    self._deliver(frame)  # decoded BGR (resized + encoded by the sender)
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
