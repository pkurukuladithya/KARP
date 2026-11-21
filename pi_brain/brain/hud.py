"""On-frame HUD drawn with OpenCV (cheap: no full-frame blending)."""

from __future__ import annotations
import time
from typing import List, Optional

import cv2
import numpy as np

from .alerts import Alert
from .lanes import LaneResult
from .tracking import VEHICLES, Track
from .vehicle_state import VehicleState

FONT = cv2.FONT_HERSHEY_SIMPLEX
COLORS = {
    "person": (0, 140, 255),
    "bicycle": (255, 200, 0),
    "motorcycle": (255, 200, 0),
    "traffic light": (0, 255, 255),
    "stop sign": (0, 0, 255),
}
VEHICLE_COLOR = (255, 170, 60)
LEVEL_COLORS = {"CRITICAL": (0, 0, 230), "WARNING": (0, 140, 255), "INFO": (200, 120, 0)}


def _text(img, s, org, scale, color, thick=1):
    cv2.putText(img, s, org, FONT, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


def draw_lanes(img: np.ndarray, lanes: Optional[LaneResult]) -> None:
    if lanes is None:
        return
    y0, y1 = lanes.y_top, lanes.y_bottom - 1
    pts = {}
    for name in ("left", "right"):
        ln = getattr(lanes, name)
        if ln is not None:
            pts[name] = ((int(LaneResult.x_at(ln, y0)), y0), (int(LaneResult.x_at(ln, y1)), y1))
    if "left" in pts and "right" in pts:
        poly = np.array([pts["left"][0], pts["right"][0], pts["right"][1], pts["left"][1]], np.int32)
        h, w = img.shape[:2]
        x_min, x_max = max(0, poly[:, 0].min()), min(w, poly[:, 0].max() + 1)
        if x_max > x_min:
            # Blend only the lane's bounding box, not the whole frame
            roi = img[y0 : y1 + 1, x_min:x_max]
            over = roi.copy()
            color = (0, 0, 255) if lanes.departure != "NONE" else (0, 200, 0)
            cv2.fillPoly(over, [poly - [x_min, y0]], color)
            cv2.addWeighted(over, 0.25, roi, 0.75, 0, dst=roi)
    for name, (p0, p1) in pts.items():
        color = (0, 0, 255) if lanes.departure == name.upper() else (0, 255, 255)
        cv2.line(img, p0, p1, color, 3, cv2.LINE_AA)


def draw_tracks(img: np.ndarray, tracks: List[Track], now: float) -> None:
    s = img.shape[1] / 640.0
    for tr in tracks:
        x1, y1, x2, y2 = tr.predict(now).astype(int)
        color = VEHICLE_COLOR if tr.label in VEHICLES else COLORS.get(tr.label, (200, 200, 200))
        if tr.ttc is not None and tr.ttc < 2.8:
            color = (0, 0, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = tr.label
        if tr.label == "traffic light" and tr.extra.get("color", "unknown") != "unknown":
            label += f" {tr.extra['color']}"
        if tr.distance is not None:
            label += f" {tr.distance:.1f}m"
        if tr.ttc is not None:
            label += f" {tr.ttc:.1f}s"
        (tw, th), _ = cv2.getTextSize(label, FONT, 0.45 * s, 1)
        ty = max(th + 4, y1)
        cv2.rectangle(img, (x1, ty - th - 4), (x1 + tw + 4, ty), color, -1)
        cv2.putText(img, label, (x1 + 2, ty - 3), FONT, 0.45 * s, (0, 0, 0), 1, cv2.LINE_AA)


def draw_status(img: np.ndarray, line: str) -> None:
    w = img.shape[1]
    s = w / 640.0
    bar_h = int(22 * s)
    img[:bar_h] = (img[:bar_h] * 0.35).astype(np.uint8)
    cv2.putText(img, line, (6, int(16 * s)), FONT, 0.45 * s, (230, 230, 230), 1, cv2.LINE_AA)


def _card(img: np.ndarray, bx: int, by: int, bw: int, bh: int, border=(60, 80, 100)) -> None:
    roi = img[by : by + bh, bx : bx + bw]
    over = np.full_like(roi, (24, 20, 16))
    cv2.addWeighted(over, 0.75, roi, 0.25, 0, dst=roi)
    cv2.rectangle(img, (bx, by), (bx + bw, by + bh), border, 1)


def draw_speed_badge(img: np.ndarray, vs: "VehicleState") -> None:
    """Speed card: real GPS speed only; otherwise "--" plus the reason (GPS CONNECTING / NO ESP32)."""
    w = img.shape[1]
    s = w / 640.0
    bx, by = int(10 * s), int(30 * s)
    bw, bh = int(95 * s), int(42 * s)
    _card(img, bx, by, bw, bh, border=vs.gps_color if vs.speed_kmh is None else (60, 80, 100))

    num_col = (0, 230, 255) if vs.speed_kmh is not None else (130, 130, 130)
    cv2.putText(img, vs.speed_text, (bx + int(8 * s), by + int(26 * s)), FONT, 0.8 * s, num_col, 2, cv2.LINE_AA)
    cv2.putText(img, "KM/H", (bx + int(52 * s), by + int(24 * s)), FONT, 0.36 * s, (0, 200, 230), 1, cv2.LINE_AA)
    status_col = vs.gps_color if vs.speed_kmh is None else (160, 180, 195)
    cv2.putText(img, vs.speed_status, (bx + int(6 * s), by + int(38 * s)), FONT, 0.28 * s, status_col, 1, cv2.LINE_AA)


def draw_road_badge(img: np.ndarray, vs: "VehicleState") -> None:
    """Road condition from the ESP32 MPU6050 (or ESP32 OFF / MPU ERROR)."""
    w = img.shape[1]
    s = w / 640.0
    bx, by = int(112 * s), int(30 * s)
    bw, bh = int(125 * s), int(42 * s)
    _card(img, bx, by, bw, bh)

    cv2.putText(img, "ROAD HEALTH", (bx + int(8 * s), by + int(14 * s)), FONT, 0.32 * s, (150, 170, 190), 1, cv2.LINE_AA)
    if vs.pothole:
        cv2.putText(img, "! POTHOLE !", (bx + int(8 * s), by + int(32 * s)), FONT, 0.45 * s, (0, 0, 255), 2, cv2.LINE_AA)
        return
    color = vs.road_color
    cv2.circle(img, (bx + int(14 * s), by + int(28 * s)), int(4 * s), color, -1)
    cv2.putText(img, vs.road_text, (bx + int(24 * s), by + int(32 * s)), FONT, 0.42 * s, color, 1, cv2.LINE_AA)


def draw_gps_badge(img: np.ndarray, vs: "VehicleState") -> None:
    """GPS / ESP32 link state, next to the speed and road cards."""
    w = img.shape[1]
    s = w / 640.0
    bx, by = int(244 * s), int(30 * s)
    text = vs.gps_text
    (tw, _), _ = cv2.getTextSize(text, FONT, 0.4 * s, 1)
    bw, bh = tw + int(30 * s), int(24 * s)
    _card(img, bx, by, bw, bh, border=vs.gps_color)
    cv2.circle(img, (bx + int(11 * s), by + bh // 2), int(4 * s), vs.gps_color, -1)
    cv2.putText(img, text, (bx + int(20 * s), by + int(17 * s)), FONT, 0.4 * s, (225, 230, 240), 1, cv2.LINE_AA)


def draw_view_mode_pill(img: np.ndarray, mode_name: str) -> None:
    """Draws a clickable hint pill in the top-right corner."""
    w = img.shape[1]
    s = w / 640.0
    pill = f"[{mode_name.upper()} | CLICK TO SWITCH]"
    (tw, _), _ = cv2.getTextSize(pill, FONT, 0.38 * s, 1)
    rx = w - tw - int(10 * s)
    ry = int(16 * s)
    cv2.putText(img, pill, (rx, ry), FONT, 0.38 * s, (0, 220, 255), 1, cv2.LINE_AA)


def draw_alerts(img: np.ndarray, alerts: List[Alert]) -> None:
    if not alerts:
        return
    h, w = img.shape[:2]
    s = w / 640.0
    blink = int(time.perf_counter() * 4) % 2 == 0
    y = h - int(12 * s)
    for a in alerts[:3]:
        color = LEVEL_COLORS[a.level]
        if a.level == "CRITICAL" and not blink:
            color = (0, 0, 120)
        scale = (0.75 if a.level == "CRITICAL" else 0.6) * s
        (tw, th), _ = cv2.getTextSize(a.text, FONT, scale, 2)
        x = (w - tw) // 2
        cv2.rectangle(img, (x - 10, y - th - 10), (x + tw + 10, y + 6), color, -1)
        cv2.putText(img, a.text, (x, y), FONT, scale, (255, 255, 255), 2, cv2.LINE_AA)
        y -= th + int(22 * s)


def no_signal_frame(w: int, h: int, msg: str) -> np.ndarray:
    img = np.zeros((h, w, 3), np.uint8)
    _text(img, msg, (20, h // 2), 0.7 * w / 640.0, (0, 200, 255), 2)
    return img
