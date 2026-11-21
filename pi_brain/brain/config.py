"""Configuration: built-in defaults, overridden by config.json, overridden by CLI flags."""

from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "camera": {
        # "0" / "/dev/video0" = USB webcam, "picam" = CSI camera (picamera2),
        # path to a video file = replay, "synthetic" = generated test road
        "source": "0",
        "width": 640,
        "height": 480,
        "fps": 30,
    },
    "detector": {
        "enabled": True,
        "backend": "auto",  # auto | ncnn | onnxruntime | opencv
        "model_onnx": "models/yolo11n_320.onnx",
        "model_ncnn": "models/yolo11n_320_ncnn",
        "input_size": 320,
        "conf_threshold": 0.35,
        "nms_threshold": 0.45,
        "threads": 3,  # leave one Pi core for camera + display
    },
    "lanes": {
        "enabled": True,
        "work_width": 320,  # lane maths runs at this width (fast), results are scaled back
        "roi_top": 0.58,  # top of the road trapezoid (fraction of frame height)
        "roi_top_width": 0.60,  # trapezoid width at the top (fraction of frame width)
        "roi_bottom_width": 1.00,  # trapezoid width at the bottom
        "hold_frames": 6,  # keep showing a lost lane this many frames
        "departure_ratio": 0.40,  # |offset| / half-lane-width that triggers a warning
    },
    "geometry": {
        "camera_height_m": 1.20,  # lens height above the road
        "pitch_deg": 0.0,  # + = camera tilted down
        "hfov_deg": 70.0,  # horizontal field of view of your camera
    },
    "alerts": {
        "ttc_critical_s": 1.6,
        "ttc_warning_s": 2.8,
        "close_vehicle_m": 6.0,
        "pedestrian_warning_m": 15.0,
        "path_left": 0.33,  # in-path corridor when lanes are not visible
        "path_right": 0.67,
        "hold_s": 0.8,  # keep an alert on screen this long after it clears (no flicker)
    },
    "display": {
        "window": True,
        "fullscreen": False,
        "mode": "vision",  # vision | map | split
        "width": 480,  # target LCD width
        "height": 320,  # target LCD height
        "dark_mode": True,  # automotive dark-theme tiles
        "web_port": 0,  # e.g. 8080 = view the HUD at http://<pi-ip>:8080 (0 = off)
        "web_fps": 12,
        "web_quality": 70,
    },
    "telemetry": {
        "speed_kmh": 48.0,
        "sim_movement": True,
        "latitude": 6.9271,
        "longitude": 79.8612,
        "zoom": 16,
    },
}


def _merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def load_config(path: str | Path | None = None) -> Dict[str, Dict[str, Any]]:
    cfg = copy.deepcopy(DEFAULTS)
    p = Path(path) if path else BASE_DIR / "config.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            _merge(cfg, json.load(f))
    return cfg


def resolve_path(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else BASE_DIR / p
