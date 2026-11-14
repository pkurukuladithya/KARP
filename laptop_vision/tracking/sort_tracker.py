"""
SORT (Simple Online and Realtime Tracking) Multi-Target Tracker.
Maintains persistent track IDs, smooths bounding boxes with Kalman filtering, and eliminates detection flicker.
"""

from __future__ import annotations
import numpy as np
from typing import List, Tuple, Optional
from shared.protocols.message_schemas import DetectedObject


def compute_iou(bb_test: Tuple[int, int, int, int], bb_gt: Tuple[int, int, int, int]) -> float:
    """Computes Intersection over Union (IoU) between two bounding boxes (xmin, ymin, xmax, ymax)."""
    xx1 = max(bb_test[0], bb_gt[0])
    yy1 = max(bb_test[1], bb_gt[1])
    xx2 = min(bb_test[2], bb_gt[2])
    yy2 = min(bb_test[3], bb_gt[3])

    w = max(0.0, xx2 - xx1)
    h = max(0.0, yy2 - yy1)
    intersection = w * h

    area1 = (bb_test[2] - bb_test[0]) * (bb_test[3] - bb_test[1])
    area2 = (bb_gt[2] - bb_gt[0]) * (bb_gt[3] - bb_gt[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


class KalmanBoxTracker:
    count = 0

    def __init__(self, bbox: Tuple[int, int, int, int], class_name: str, confidence: float):
        self.id = KalmanBoxTracker.count
        KalmanBoxTracker.count += 1

        self.class_name = class_name
        self.confidence = confidence
        self.time_since_update = 0
        self.hits = 1
        self.hit_streak = 1
        self.age = 0

        # State: [x_center, y_center, width, height, vx, vy]
        xmin, ymin, xmax, ymax = bbox
        self.x = float((xmin + xmax) / 2.0)
        self.y = float((ymin + ymax) / 2.0)
        self.w = float(xmax - xmin)
        self.h = float(ymax - ymin)
        self.vx = 0.0
        self.vy = 0.0

    def predict(self) -> Tuple[int, int, int, int]:
        self.x += self.vx
        self.y += self.vy
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        return self.get_bbox()

    def update(self, bbox: Tuple[int, int, int, int], confidence: float) -> None:
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1
        self.confidence = confidence

        xmin, ymin, xmax, ymax = bbox
        new_x = float((xmin + xmax) / 2.0)
        new_y = float((ymin + ymax) / 2.0)
        new_w = float(xmax - xmin)
        new_h = float(ymax - ymin)

        # Simple alpha-beta tracking filter
        self.vx = 0.7 * self.vx + 0.3 * (new_x - self.x)
        self.vy = 0.7 * self.vy + 0.3 * (new_y - self.y)
        self.x = 0.6 * self.x + 0.4 * new_x
        self.y = 0.6 * self.y + 0.4 * new_y
        self.w = 0.7 * self.w + 0.3 * new_w
        self.h = 0.7 * self.h + 0.3 * new_h

    def get_bbox(self) -> Tuple[int, int, int, int]:
        xmin = int(self.x - self.w / 2.0)
        ymin = int(self.y - self.h / 2.0)
        xmax = int(self.x + self.w / 2.0)
        ymax = int(self.y + self.h / 2.0)
        return (xmin, ymin, xmax, ymax)


class SortTracker:
    def __init__(self, max_age: int = 4, min_hits: int = 1, iou_threshold: float = 0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.trackers: List[KalmanBoxTracker] = []

    def update(self, detections: List[DetectedObject]) -> List[DetectedObject]:
        """
        Updates trackers with newly detected objects.
        Returns tracked objects with stabilized IDs.
        """
        # 1. Predict new locations
        for trk in self.trackers:
            trk.predict()

        # 2. Match detections to trackers using greedy IoU
        matched_trks = set()
        matched_dets = set()
        matches = []

        if self.trackers and detections:
            # Build IoU matrix
            iou_matrix = np.zeros((len(detections), len(self.trackers)), dtype=np.float32)
            for d_idx, det in enumerate(detections):
                for t_idx, trk in enumerate(self.trackers):
                    if det.class_name == trk.class_name:
                        iou_matrix[d_idx, t_idx] = compute_iou(det.bbox, trk.get_bbox())
                    else:
                        iou_matrix[d_idx, t_idx] = 0.0

            # Greedy match from highest IoU down
            while True:
                max_val = np.max(iou_matrix)
                if max_val < self.iou_threshold:
                    break
                d_idx, t_idx = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)
                matches.append((d_idx, t_idx))
                matched_dets.add(d_idx)
                matched_trks.add(t_idx)
                iou_matrix[d_idx, :] = -1.0
                iou_matrix[:, t_idx] = -1.0

        # 3. Update matched trackers
        for d_idx, t_idx in matches:
            det = detections[d_idx]
            self.trackers[t_idx].update(det.bbox, det.confidence)

        # 4. Create new trackers for unmatched detections
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_dets:
                self.trackers.append(KalmanBoxTracker(det.bbox, det.class_name, det.confidence))

        # 5. Extract active tracks and prune dead ones
        active_tracks: List[DetectedObject] = []
        surviving_trackers: List[KalmanBoxTracker] = []

        for trk in self.trackers:
            if trk.time_since_update <= self.max_age:
                surviving_trackers.append(trk)
                if trk.hits >= self.min_hits or trk.time_since_update == 0:
                    active_tracks.append(
                        DetectedObject(
                            id=trk.id,
                            class_name=trk.class_name,
                            confidence=round(trk.confidence, 2),
                            bbox=trk.get_bbox(),
                        )
                    )

        self.trackers = surviving_trackers
        return active_tracks
