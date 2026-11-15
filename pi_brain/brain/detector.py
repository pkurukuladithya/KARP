"""
CPU object detector for Raspberry Pi: YOLO11n (COCO) at 320x320.

Backends, fastest first on a Pi 4B:
  ncnn         - Tencent NCNN, ARM NEON optimised (pip install ncnn)
  onnxruntime  - Microsoft ONNX Runtime (pip install onnxruntime, 64-bit OS only)
  opencv       - cv2.dnn fallback, works everywhere but slowest
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .config import resolve_path

logger = logging.getLogger("pi_brain.detector")

# COCO class id -> label for the classes an ADAS cares about
ADAS_CLASSES: Dict[int, str] = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    9: "traffic light",
    11: "stop sign",
}
_KEEP_IDS = np.array(sorted(ADAS_CLASSES), dtype=np.int64)


@dataclass
class Detection:
    box: np.ndarray  # float32 [x1, y1, x2, y2] in frame pixels
    score: float
    label: str
    extra: Dict[str, str] = field(default_factory=dict)


def letterbox(img: np.ndarray, size: int) -> Tuple[np.ndarray, float, Tuple[int, int]]:
    """Resize keeping aspect ratio into a size x size grey canvas."""
    h, w = img.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[py : py + nh, px : px + nw] = resized
    return canvas, scale, (px, py)


def postprocess(
    out: np.ndarray,
    scale: float,
    pad: Tuple[int, int],
    frame_shape: Tuple[int, int],
    conf: float,
    nms: float,
) -> List[Detection]:
    """Decodes a YOLOv8/YOLO11 head output of shape (84, N) or (1, 84, N)."""
    pred = np.asarray(out, dtype=np.float32).reshape(-1, out.shape[-1])  # (84, N)
    if pred.shape[0] != 84 and pred.shape[1] == 84:
        pred = pred.T
    cls_scores = pred[4:][_KEEP_IDS]  # only ADAS classes: (K, N)
    best = cls_scores.argmax(0)
    score = cls_scores[best, np.arange(cls_scores.shape[1])]
    keep = score >= conf
    if not np.any(keep):
        return []
    cx, cy, bw, bh = pred[0, keep], pred[1, keep], pred[2, keep], pred[3, keep]
    score, cls_id = score[keep], _KEEP_IDS[best[keep]]

    h, w = frame_shape
    x1 = np.clip((cx - bw / 2 - pad[0]) / scale, 0, w - 1)
    y1 = np.clip((cy - bh / 2 - pad[1]) / scale, 0, h - 1)
    x2 = np.clip((cx + bw / 2 - pad[0]) / scale, 0, w - 1)
    y2 = np.clip((cy + bh / 2 - pad[1]) / scale, 0, h - 1)

    # Class-aware NMS: shift each class into its own coordinate block
    off = cls_id.astype(np.float32) * 4096.0
    rects = np.stack([x1 + off, y1 + off, x2 - x1, y2 - y1], axis=1).tolist()
    idx = cv2.dnn.NMSBoxes(rects, score.tolist(), conf, nms)
    idx = np.array(idx).reshape(-1) if len(idx) else []

    dets: List[Detection] = []
    for i in idx:
        if x2[i] - x1[i] < 3 or y2[i] - y1[i] < 3:
            continue
        dets.append(
            Detection(
                box=np.array([x1[i], y1[i], x2[i], y2[i]], np.float32),
                score=float(score[i]),
                label=ADAS_CLASSES[int(cls_id[i])],
            )
        )
    return dets


def traffic_light_color(frame: np.ndarray, box: np.ndarray) -> str:
    x1, y1, x2, y2 = box.astype(int)
    crop = frame[max(0, y1) : y2, max(0, x1) : x2]
    if crop.size < 30:
        return "unknown"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    lit = cv2.inRange(hsv, (0, 90, 140), (180, 255, 255))
    hue = hsv[..., 0][lit > 0]
    if hue.size < max(4, crop.shape[0] * crop.shape[1] * 0.02):
        return "unknown"
    red = np.count_nonzero((hue < 10) | (hue > 165))
    yellow = np.count_nonzero((hue >= 12) & (hue <= 35))
    green = np.count_nonzero((hue >= 45) & (hue <= 95))
    return ("red", "yellow", "green")[int(np.argmax([red, yellow, green]))]


class YoloDetector:
    def __init__(self, cfg: dict):
        self.size = int(cfg.get("input_size", 320))
        self.conf = float(cfg.get("conf_threshold", 0.35))
        self.nms = float(cfg.get("nms_threshold", 0.45))
        self.threads = int(cfg.get("threads", 3))
        self.backend = "none"
        self._run = None

        self.timings: Dict[str, float] = {}

        wanted = str(cfg.get("backend", "auto")).lower()
        order = ["ncnn", "onnxruntime", "opencv"] if wanted == "auto" else [wanted]
        errors = []
        best = None
        dummy = np.random.default_rng(0).integers(0, 255, (self.size, self.size, 3), dtype=np.uint8)
        for name in order:
            try:
                getattr(self, f"_init_{name}")(cfg)
            except Exception as e:
                errors.append(f"{name}: {e}")
                continue
            if wanted != "auto":
                best = (name, self._run)
                break
            # Auto: time each available backend on this machine and keep the fastest
            ms = self._time_backend(dummy)
            self.timings[name] = ms
            logger.info(f"  backend {name:<12} {ms:6.1f} ms / frame")
            if best is None or ms < self.timings[best[0]]:
                best = (name, self._run)
        if best is None:
            raise RuntimeError("No detector backend could be loaded -> " + " | ".join(errors))
        self.backend, self._run = best
        logger.info(f"Detector ready: backend={self.backend}, input {self.size}x{self.size}, threads {self.threads}")

    def _time_backend(self, img: np.ndarray, runs: int = 5) -> float:
        import time

        blob = cv2.dnn.blobFromImage(img, 1.0 / 255.0, swapRB=True)
        self._run(blob)  # warm-up (allocations, kernel selection)
        t = time.perf_counter()
        for _ in range(runs):
            self._run(blob)
        return (time.perf_counter() - t) * 1000.0 / runs

    # -------------------------------------------------------------- backends
    def _init_ncnn(self, cfg: dict) -> None:
        import ncnn  # type: ignore

        d = resolve_path(cfg.get("model_ncnn", "models/yolo11n_320_ncnn"))
        param, binf = d / "model.ncnn.param", d / "model.ncnn.bin"
        if not param.exists() or not binf.exists():
            raise FileNotFoundError(f"{d} missing model.ncnn.param/bin")
        net = ncnn.Net()
        net.opt.use_vulkan_compute = False
        net.opt.num_threads = self.threads
        net.opt.use_fp16_storage = True
        net.opt.use_fp16_arithmetic = False
        if net.load_param(str(param)) != 0 or net.load_model(str(binf)) != 0:
            raise RuntimeError("failed to load NCNN model")
        self._ncnn_net = net

        def run(blob: np.ndarray) -> np.ndarray:
            ex = net.create_extractor()
            ex.input("in0", ncnn.Mat(blob[0]))
            ret, out = ex.extract("out0")
            if ret != 0:
                raise RuntimeError(f"NCNN extract failed ({ret})")
            return np.array(out)

        self._run = run

    def _init_onnxruntime(self, cfg: dict) -> None:
        import onnxruntime as ort  # type: ignore

        path = resolve_path(cfg.get("model_onnx", "models/yolo11n_320.onnx"))
        if not path.exists():
            raise FileNotFoundError(str(path))
        so = ort.SessionOptions()
        so.intra_op_num_threads = self.threads
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess = ort.InferenceSession(str(path), sess_options=so, providers=["CPUExecutionProvider"])
        name = sess.get_inputs()[0].name
        self._run = lambda blob: sess.run(None, {name: blob})[0]

    def _init_opencv(self, cfg: dict) -> None:
        path = resolve_path(cfg.get("model_onnx", "models/yolo11n_320.onnx"))
        if not path.exists():
            raise FileNotFoundError(str(path))
        net = cv2.dnn.readNetFromONNX(str(path))

        def run(blob: np.ndarray) -> np.ndarray:
            net.setInput(blob)
            return net.forward()

        self._run = run

    # -------------------------------------------------------------- inference
    def detect(self, frame: np.ndarray) -> List[Detection]:
        img, scale, pad = letterbox(frame, self.size)
        blob = cv2.dnn.blobFromImage(img, 1.0 / 255.0, swapRB=True)  # (1,3,S,S) float32 RGB
        out = self._run(blob)
        dets = postprocess(out, scale, pad, frame.shape[:2], self.conf, self.nms)
        for d in dets:
            if d.label == "traffic light":
                d.extra["color"] = traffic_light_color(frame, d.box)
        return dets


def available_backends() -> List[str]:
    found = []
    for mod, name in (("ncnn", "ncnn"), ("onnxruntime", "onnxruntime")):
        try:
            __import__(mod)
            found.append(name)
        except Exception:
            pass
    found.append("opencv")
    return found


def model_files_present(cfg: dict) -> Optional[str]:
    """Returns an error string if no model file exists for any backend."""
    onnx = resolve_path(cfg.get("model_onnx", ""))
    ncnn_dir = resolve_path(cfg.get("model_ncnn", ""))
    if onnx.exists() or (Path(ncnn_dir) / "model.ncnn.param").exists():
        return None
    return f"No model found ({onnx} / {ncnn_dir}). Run tools/export_model.py on the laptop or `git pull`."
