"""
Lightweight IoU tracker + monocular distance / time-to-collision estimation.

Pure numpy (no scipy), cheap enough for the Pi. Each track also keeps a pixel
velocity so the display can move boxes smoothly BETWEEN detector updates.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .detector import Detection

VEHICLES = {"car", "truck", "bus", "motorcycle", "bicycle"}

# Typical real-world heights (m), used when the ground-plane method is not usable
REAL_HEIGHT_M = {
    "person": 1.70,
    "bicycle": 1.10,
    "motorcycle": 1.20,
    "car": 1.50,
    "bus": 3.20,
    "truck": 3.00,
    "traffic light": 0.90,
    "stop sign": 0.75,
}


class DistanceEstimator:
    """Flat-road pinhole model: Z = H / tan(pitch + atan((y_bottom - cy) / f))."""

    def __init__(self, width: int, height: int, camera_height_m: float, pitch_deg: float, hfov_deg: float):
        self.f = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        self.cy = height / 2.0
        self.cam_h = camera_height_m
        self.pitch = math.radians(pitch_deg)

    def horizon_y(self) -> float:
        return self.cy - self.f * math.tan(self.pitch)

    def estimate(self, box: np.ndarray, label: str) -> float:
        x1, y1, x2, y2 = (float(v) for v in box)
        if label in VEHICLES or label == "person":
            angle = self.pitch + math.atan((y2 - self.cy) / self.f)
            if angle > math.radians(0.8):  # bottom clearly below the horizon
                return float(np.clip(self.cam_h / math.tan(angle), 0.5, 150.0))
        h_px = max(1.0, y2 - y1)
        return float(np.clip(self.f * REAL_HEIGHT_M.get(label, 1.5) / h_px, 0.5, 150.0))


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), np.float32)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-6)


@dataclass
class Track:
    track_id: int
    box: np.ndarray
    label: str
    score: float
    t: float  # capture time of the frame this box belongs to
    hits: int = 1
    misses: int = 0
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(4, np.float32))  # px/s for each box edge
    distance: Optional[float] = None
    closing_speed: float = 0.0  # m/s, + = getting closer
    ttc: Optional[float] = None
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def confirmed(self) -> bool:
        return self.hits >= 2

    def predict(self, t_now: float, max_dt: float = 0.4) -> np.ndarray:
        dt = min(max(0.0, t_now - self.t), max_dt)
        return self.box + self.velocity * dt


def _compatible(a: str, b: str) -> bool:
    return a == b or (a in VEHICLES and b in VEHICLES)


class Tracker:
    def __init__(self, iou_threshold: float = 0.25, max_misses: int = 4):
        self.iou_threshold = iou_threshold
        self.max_misses = max_misses
        self.tracks: List[Track] = []
        self._next_id = 1
        self.estimator: Optional[DistanceEstimator] = None

    def update(self, dets: List[Detection], t: float) -> List[Track]:
        tracks = self.tracks
        boxes_t = np.array([tr.predict(t) for tr in tracks], np.float32).reshape(-1, 4)
        boxes_d = np.array([d.box for d in dets], np.float32).reshape(-1, 4)
        iou = iou_matrix(boxes_t, boxes_d)

        matched_t, matched_d = set(), set()
        if iou.size:
            order = np.dstack(np.unravel_index(np.argsort(-iou, axis=None), iou.shape))[0]
            for ti, di in order:
                if iou[ti, di] < self.iou_threshold:
                    break
                if ti in matched_t or di in matched_d or not _compatible(tracks[ti].label, dets[di].label):
                    continue
                matched_t.add(ti)
                matched_d.add(di)
                self._update_track(tracks[ti], dets[di], t)

        for di, d in enumerate(dets):
            if di not in matched_d:
                tr = Track(self._next_id, d.box.copy(), d.label, d.score, t, extra=dict(d.extra))
                self._next_id += 1
                self._update_distance(tr, None)
                tracks.append(tr)

        for ti, tr in enumerate(tracks):
            if ti not in matched_t and tr.t != t:
                tr.misses += 1
        self.tracks = [tr for tr in tracks if tr.misses <= self.max_misses]
        return [tr for tr in self.tracks if tr.confirmed and tr.misses == 0]

    def _update_track(self, tr: Track, d: Detection, t: float) -> None:
        dt = t - tr.t
        if dt > 1e-3:
            v = (d.box - tr.box) / dt
            tr.velocity = 0.5 * tr.velocity + 0.5 * np.clip(v, -2000, 2000)
        prev_dist, prev_t = tr.distance, tr.t
        tr.box = 0.3 * tr.box + 0.7 * d.box  # light smoothing against box jitter
        tr.score = d.score
        if d.label != tr.label and d.score > 0.5:
            tr.label = d.label
        tr.extra.update(d.extra)
        tr.t = t
        tr.hits += 1
        tr.misses = 0
        self._update_distance(tr, (prev_dist, prev_t))

    def _update_distance(self, tr: Track, prev) -> None:
        if self.estimator is None:
            return
        raw = self.estimator.estimate(tr.box, tr.label)
        if prev is None or prev[0] is None:
            tr.distance = raw
            return
        prev_dist, prev_t = prev
        tr.distance = 0.6 * prev_dist + 0.4 * raw
        dt = tr.t - prev_t
        if dt > 1e-3:
            speed = (prev_dist - tr.distance) / dt
            tr.closing_speed = 0.7 * tr.closing_speed + 0.3 * speed
        tr.ttc = tr.distance / tr.closing_speed if tr.closing_speed > 0.5 and tr.hits >= 4 else None
