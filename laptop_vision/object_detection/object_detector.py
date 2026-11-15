"""
GPU Object Detector (Ultralytics YOLO on NVIDIA CUDA) with SORT tracking,
calibrated monocular distance and smoothed Time-To-Collision.

Runs YOLO11 (COCO) in FP16 on the RTX 4050. Falls back to CPU only if CUDA is
unavailable, and reports "NO MODEL" (no detections) instead of fabricating
detections if ultralytics / weights are missing.
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

from shared.protocols.message_schemas import DetectedObject
from .distance_estimator import CalibratedMonocularDistanceEstimator
from laptop_vision.tracking.sort_tracker import SortTracker

logger = logging.getLogger("KARP.ObjectDetector")

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
DEFAULT_MODEL = "yolo11s.pt"

# COCO class id -> KARP class name
COCO_TO_KARP: Dict[int, str] = {
    0: "pedestrian",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    9: "traffic light",
    11: "stop sign",
}


class ADASObjectDetector:
    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: float = 0.45,
        iou_threshold: float = 0.45,
        use_cuda: bool = True,
        imgsz: int = 640,
        camera_height_m: float = 1.25,
        camera_pitch_deg: float = 2.0,
        focal_length_px: float = 920.0,
    ):
        self.conf_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.use_cuda = use_cuda
        self.imgsz = imgsz
        self.device_name = "NO MODEL"
        self.model = None
        self._device = "cpu"
        self._predict_precision: dict = {}

        self.tracker = SortTracker(max_age=5, min_hits=2, iou_threshold=0.3)
        self.dist_estimator = CalibratedMonocularDistanceEstimator(
            camera_height_m=camera_height_m,
            camera_pitch_deg=camera_pitch_deg,
            focal_length_px=focal_length_px,
        )
        # track_id -> (smoothed_dist_m, timestamp_s, smoothed_closing_speed_mps)
        self._dist_state: Dict[int, Tuple[float, float, float]] = {}
        self._init_backend(model_path)

    # ------------------------------------------------------------------ setup
    def _init_backend(self, model_path: Optional[str]) -> None:
        try:
            import torch
            from ultralytics import YOLO
        except ImportError as e:
            logger.error(
                f"Ultralytics/PyTorch not available ({e}). Object detection DISABLED. "
                "Install with: pip install ultralytics  (and CUDA PyTorch, see laptop_vision/requirements.txt)"
            )
            return

        if self.use_cuda and torch.cuda.is_available():
            self._device = "cuda:0"
            self.device_name = f"{torch.cuda.get_device_name(0)} (CUDA FP16)"
        else:
            self._device = "cpu"
            self.device_name = "CPU (no CUDA!)"
            if self.use_cuda:
                logger.warning(
                    "CUDA requested but torch.cuda.is_available() is False. "
                    "You have a CPU-only PyTorch build. Install: "
                    "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128"
                )

        path = Path(model_path) if model_path else MODELS_DIR / DEFAULT_MODEL
        if not path.is_absolute() and not path.exists():
            path = MODELS_DIR / path.name
        try:
            if not path.exists():
                from ultralytics.utils.downloads import attempt_download_asset
                logger.info(f"Downloading model weights {path.name} -> {path.parent}")
                path.parent.mkdir(parents=True, exist_ok=True)
                attempt_download_asset(str(path))
            self.model = YOLO(str(path))
        except Exception as e:
            logger.error(f"Failed to load YOLO model {path}: {e}. Object detection DISABLED.")
            self.model = None
            self.device_name = "NO MODEL"
            return

        # Choose precision argument compatible with installed ultralytics version
        if self._device.startswith("cuda"):
            for candidate in ({"quantize": 16}, {"half": True}):
                try:
                    self._warmup(candidate)
                    self._predict_precision = candidate
                    break
                except Exception:
                    continue
        else:
            self._warmup({})

        logger.info(f"YOLO model {path.name} loaded on {self.device_name}")

    def _warmup(self, precision_kwargs: dict) -> None:
        dummy = np.zeros((540, 960, 3), dtype=np.uint8)
        for _ in range(3):
            self.model.predict(
                dummy, device=self._device, imgsz=self.imgsz, verbose=False, **precision_kwargs
            )

    def set_confidence_threshold(self, conf: float) -> None:
        self.conf_threshold = max(0.1, min(0.95, conf))

    # -------------------------------------------------------------- inference
    def detect_and_track(self, frame_bgr: np.ndarray, timestamp_ms: int) -> List[DetectedObject]:
        """Runs YOLO on GPU, SORT tracking, distance and smoothed TTC."""
        h, w = frame_bgr.shape[:2]
        raw = self._detect_raw(frame_bgr)
        tracked = self.tracker.update(raw)

        t_now = timestamp_ms / 1000.0  # Pi capture clock -> consistent dt between frames
        alive_ids = set()
        for obj in tracked:
            alive_ids.add(obj.id)
            if obj.class_name in ("traffic light", "stop sign"):
                continue
            dist = self.dist_estimator.estimate_distance(obj.bbox, img_w=w, img_h=h)
            if dist is None:
                obj.estimated_distance_m = None
                self._dist_state.pop(obj.id, None)
                continue

            prev = self._dist_state.get(obj.id)
            if prev is None:
                self._dist_state[obj.id] = (dist, t_now, 0.0)
                obj.estimated_distance_m = dist
                continue

            prev_dist, prev_t, prev_speed = prev
            dt = t_now - prev_t
            if dt <= 0.0 or dt > 1.0:
                self._dist_state[obj.id] = (dist, t_now, 0.0)
                obj.estimated_distance_m = dist
                continue

            smoothed = 0.6 * prev_dist + 0.4 * dist
            inst_speed = (prev_dist - smoothed) / dt  # positive when approaching
            speed = 0.8 * prev_speed + 0.2 * inst_speed
            self._dist_state[obj.id] = (smoothed, t_now, speed)

            obj.estimated_distance_m = round(smoothed, 1)
            obj.ttc_sec = self.dist_estimator.ttc_from_speed(smoothed, speed)

        # Prune state of dead tracks
        for tid in list(self._dist_state.keys()):
            if tid not in alive_ids:
                del self._dist_state[tid]

        return tracked

    def _detect_raw(self, frame_bgr: np.ndarray) -> List[DetectedObject]:
        if self.model is None:
            return []

        results = self.model.predict(
            frame_bgr,
            device=self._device,
            imgsz=self.imgsz,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            classes=list(COCO_TO_KARP.keys()),
            verbose=False,
            **self._predict_precision,
        )
        if not results:
            return []

        data = results[0].boxes.data
        if data is None or len(data) == 0:
            return []
        arr = data.float().cpu().numpy()  # [N, 6] = x1, y1, x2, y2, conf, cls

        detections: List[DetectedObject] = []
        for i, (x1, y1, x2, y2, conf, cls) in enumerate(arr[:, :6]):
            name = COCO_TO_KARP.get(int(cls))
            if name is None:
                continue
            detections.append(
                DetectedObject(
                    id=i,
                    class_name=name,
                    confidence=round(float(conf), 2),
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                )
            )
        return detections
