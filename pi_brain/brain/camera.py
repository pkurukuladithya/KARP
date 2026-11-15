"""
Threaded camera source that always exposes only the NEWEST frame.

The capture thread reads at the camera's own rate; consumers (detector thread,
display loop) pick up the latest frame and never queue old ones, so latency stays
at one frame no matter how slow a consumer is.
"""

from __future__ import annotations
import logging
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("pi_brain.camera")

Frame = Tuple[np.ndarray, int, float]  # (bgr image, frame id, capture time monotonic)


class Camera(threading.Thread):
    def __init__(self, source: str = "0", width: int = 640, height: int = 480, fps: int = 30):
        super().__init__(daemon=True, name="Camera")
        self.source = str(source)
        self.width, self.height, self.fps = int(width), int(height), int(fps)
        self._cond = threading.Condition()
        self._frame: Optional[np.ndarray] = None
        self._frame_id = 0
        self._frame_t = 0.0
        self._running = True
        self.connected = False
        self.capture_fps = 0.0
        self.description = self.source

    # ------------------------------------------------------------------ consumer API
    def latest(self) -> Optional[Frame]:
        with self._cond:
            if self._frame is None:
                return None
            return self._frame, self._frame_id, self._frame_t

    def wait_new(self, last_id: int, timeout: float = 1.0) -> Optional[Frame]:
        """Blocks until a frame newer than `last_id` exists (or timeout)."""
        with self._cond:
            self._cond.wait_for(lambda: self._frame_id != last_id or not self._running, timeout)
            if self._frame is None or self._frame_id == last_id:
                return None
            return self._frame, self._frame_id, self._frame_t

    def stop(self) -> None:
        self._running = False
        with self._cond:
            self._cond.notify_all()

    # ------------------------------------------------------------------ producer
    def _publish(self, frame: np.ndarray) -> None:
        with self._cond:
            self._frame = frame
            self._frame_id += 1
            self._frame_t = time.perf_counter()
            self._cond.notify_all()

    def run(self) -> None:
        src = self.source.lower()
        if src == "synthetic":
            self._run_synthetic()
        elif src in ("picam", "picamera", "csi"):
            self._run_picamera()
        elif Path(self.source).is_file():
            self._run_file()
        else:
            self._run_v4l2()

    def _tick_fps(self, state: dict) -> None:
        state["n"] += 1
        now = time.perf_counter()
        if now - state["t"] >= 1.0:
            self.capture_fps = state["n"] / (now - state["t"])
            state["n"], state["t"] = 0, now

    # USB webcam ---------------------------------------------------------------------
    def _open_usb(self) -> Optional[cv2.VideoCapture]:
        dev: object = int(self.source) if self.source.isdigit() else self.source
        on_linux = platform.system() == "Linux"
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2) if on_linux else cv2.VideoCapture(dev)
        if not cap.isOpened():
            cap.release()
            return None
        # MJPG lets USB 2.0 deliver 30 fps; buffer of 1 = no stale frames queued in the driver
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if on_linux:
            # Stop the webcam from dropping to 5-15 fps in dim light (exposure priority)
            node = f"/dev/video{self.source}" if self.source.isdigit() else self.source
            for ctrl in ("exposure_dynamic_framerate=0", "exposure_auto_priority=0"):
                try:
                    subprocess.run(["v4l2-ctl", "-d", node, "-c", ctrl], capture_output=True, timeout=2)
                except Exception:
                    pass
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.description = f"USB camera {self.source} {w}x{h}"
        logger.info(f"Opened {self.description} (requested {self.width}x{self.height}@{self.fps})")
        return cap

    def _run_v4l2(self) -> None:
        stat = {"n": 0, "t": time.perf_counter()}
        cap = None
        fails = 0
        while self._running:
            if cap is None:
                cap = self._open_usb()
                if cap is None:
                    self.connected = False
                    logger.warning(f"Camera '{self.source}' not available - retrying in 2 s")
                    time.sleep(2.0)
                    continue
                self.connected = True
            ok, frame = cap.read()
            if not ok or frame is None:
                fails += 1
                if fails > 30:
                    logger.warning("Camera stopped delivering frames - reopening")
                    cap.release()
                    cap = None
                    fails = 0
                    self.connected = False
                time.sleep(0.01)
                continue
            fails = 0
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)
            self._publish(frame)
            self._tick_fps(stat)
        if cap is not None:
            cap.release()

    # CSI camera (Raspberry Pi Camera Module) -----------------------------------------
    def _run_picamera(self) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore
        except ImportError:
            logger.error("picamera2 not installed (sudo apt install python3-picamera2). Falling back to USB 0.")
            self.source = "0"
            self._run_v4l2()
            return
        cam = Picamera2()
        cam.configure(
            cam.create_video_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"},
                controls={"FrameRate": self.fps},
                buffer_count=2,
            )
        )
        cam.start()
        self.connected = True
        self.description = f"Pi camera {self.width}x{self.height}"
        logger.info(f"Opened {self.description}")
        stat = {"n": 0, "t": time.perf_counter()}
        try:
            while self._running:
                frame = cam.capture_array("main")  # RGB888 in picamera2 = BGR byte order for OpenCV
                self._publish(frame)
                self._tick_fps(stat)
        finally:
            cam.stop()

    # Video file replay ----------------------------------------------------------------
    def _run_file(self) -> None:
        cap = cv2.VideoCapture(self.source)
        src_fps = cap.get(cv2.CAP_PROP_FPS) or self.fps
        period = 1.0 / max(1.0, min(src_fps, 60.0))
        self.connected = cap.isOpened()
        self.description = f"file {Path(self.source).name}"
        logger.info(f"Replaying {self.source} at {1 / period:.0f} fps (looping)")
        stat = {"n": 0, "t": time.perf_counter()}
        next_t = time.perf_counter()
        while self._running:
            ok, frame = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)
            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()
            self._publish(frame)
            self._tick_fps(stat)
        cap.release()

    # Synthetic road (testing without a camera) --------------------------------------------
    def _run_synthetic(self) -> None:
        self.connected = True
        self.description = "synthetic road"
        period = 1.0 / self.fps
        stat = {"n": 0, "t": time.perf_counter()}
        k = 0
        next_t = time.perf_counter()
        while self._running:
            self._publish(synthetic_road(self.width, self.height, k))
            self._tick_fps(stat)
            k += 1
            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()


def synthetic_road(w: int, h: int, k: int = 0, drift: float = 0.0) -> np.ndarray:
    """Simple perspective road with a solid left line and a dashed right line."""
    img = np.zeros((h, w, 3), np.uint8)
    horizon = int(h * 0.55)
    img[:horizon] = (170, 130, 90)  # sky
    img[horizon:] = (70, 70, 70)  # asphalt
    vx = w // 2 + int(drift * w)
    left_bot, right_bot = int(w * 0.12), int(w * 0.88)
    sway = int(np.sin(k / 40.0) * w * 0.03)
    cv2.line(img, (vx - 6, horizon), (left_bot + sway, h), (235, 235, 235), 6)
    for i in range(10):  # dashed right line, animated
        t0 = ((i + (k % 20) / 20.0) / 10.0) ** 1.6
        t1 = min(1.0, t0 + 0.05)
        p0 = (int(vx + 6 + (right_bot + sway - vx - 6) * t0), int(horizon + (h - horizon) * t0))
        p1 = (int(vx + 6 + (right_bot + sway - vx - 6) * t1), int(horizon + (h - horizon) * t1))
        cv2.line(img, p0, p1, (235, 235, 235), 6)
    return img
