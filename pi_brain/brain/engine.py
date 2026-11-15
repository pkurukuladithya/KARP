"""
Background detection worker.

Runs YOLO on the newest camera frame as fast as the CPU allows (typically 6-12 Hz
on a Pi 4B) while the display loop keeps running at camera speed. Frames that
arrive while a detection is in progress are simply skipped - never queued.
"""

from __future__ import annotations
import copy
import logging
import threading
import time
from typing import List, Optional

from .camera import Camera
from .detector import YoloDetector
from .tracking import DistanceEstimator, Track, Tracker

logger = logging.getLogger("pi_brain.engine")


class DetectorWorker(threading.Thread):
    def __init__(self, camera: Camera, detector: YoloDetector, geometry: dict):
        super().__init__(daemon=True, name="Detector")
        self.camera = camera
        self.detector = detector
        self.geometry = geometry
        self.tracker = Tracker()
        self._lock = threading.Lock()
        self._tracks: List[Track] = []
        self._running = True
        self.enabled = True
        self.fps = 0.0
        self.infer_ms = 0.0
        self.age_ms = 0.0  # capture-to-result delay of the latest detections

    def snapshot(self) -> List[Track]:
        with self._lock:
            return self._tracks

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        last_id = 0
        n, t_stat = 0, time.perf_counter()
        while self._running:
            if not self.enabled:
                with self._lock:
                    self._tracks = []
                time.sleep(0.1)
                continue
            item = self.camera.wait_new(last_id, timeout=0.5)
            if item is None:
                continue
            frame, last_id, t_cap = item
            if self.tracker.estimator is None:
                g = self.geometry
                self.tracker.estimator = DistanceEstimator(
                    frame.shape[1], frame.shape[0], g["camera_height_m"], g["pitch_deg"], g["hfov_deg"]
                )
            t0 = time.perf_counter()
            try:
                dets = self.detector.detect(frame)
            except Exception as e:
                logger.exception(f"Detection failed: {e}")
                time.sleep(0.5)
                continue
            tracks = self.tracker.update(dets, t_cap)
            done = time.perf_counter()
            self.infer_ms = 0.8 * self.infer_ms + 0.2 * (done - t0) * 1000 if self.infer_ms else (done - t0) * 1000
            self.age_ms = (done - t_cap) * 1000
            # Publish immutable copies so the display thread never sees half-updated tracks
            published = [copy.copy(tr) for tr in tracks]
            for tr in published:
                tr.box, tr.velocity, tr.extra = tr.box.copy(), tr.velocity.copy(), dict(tr.extra)
            with self._lock:
                self._tracks = published
            n += 1
            if done - t_stat >= 1.0:
                self.fps, n, t_stat = n / (done - t_stat), 0, done


def read_cpu_temp() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None
