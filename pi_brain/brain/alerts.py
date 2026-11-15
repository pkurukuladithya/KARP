"""ADAS warning logic: forward collision, pedestrian in path, lane departure, signs/lights."""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .lanes import LaneResult
from .tracking import VEHICLES, Track

LEVEL_RANK = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


@dataclass
class Alert:
    key: str
    level: str  # CRITICAL | WARNING | INFO
    text: str


def in_path(tr: Track, lanes: Optional[LaneResult], w: int, cfg: dict) -> bool:
    """Is the object's ground point inside our lane (or the centre corridor if no lanes)?"""
    x1, _, x2, y2 = (float(v) for v in tr.box)
    cx = (x1 + x2) / 2
    if lanes is not None and lanes.both and lanes.stable:
        xl, xr = LaneResult.x_at(lanes.left, y2), LaneResult.x_at(lanes.right, y2)
        margin = 0.1 * (xr - xl)
        return xl - margin <= cx <= xr + margin
    return cfg["path_left"] * w <= cx <= cfg["path_right"] * w


def evaluate(tracks: List[Track], lanes: Optional[LaneResult], w: int, cfg: dict) -> List[Alert]:
    out: List[Alert] = []
    nearest_vehicle = None
    for tr in tracks:
        if tr.distance is None:
            continue
        if tr.label in VEHICLES and in_path(tr, lanes, w, cfg):
            if nearest_vehicle is None or tr.distance < nearest_vehicle.distance:
                nearest_vehicle = tr
        elif tr.label == "person" and in_path(tr, lanes, w, cfg) and tr.distance < cfg["pedestrian_warning_m"]:
            lvl = "CRITICAL" if tr.distance < cfg["pedestrian_warning_m"] / 2 else "WARNING"
            out.append(Alert("ped", lvl, f"PEDESTRIAN AHEAD  {tr.distance:.1f} m"))
        elif tr.label == "stop sign" and tr.distance < 30:
            out.append(Alert("stop", "INFO", f"STOP SIGN  {tr.distance:.0f} m"))
        elif tr.label == "traffic light" and tr.extra.get("color") == "red" and tr.distance < 40:
            out.append(Alert("red", "WARNING", "RED LIGHT AHEAD"))

    v = nearest_vehicle
    if v is not None:
        if v.ttc is not None and v.ttc < cfg["ttc_critical_s"]:
            out.append(Alert("fcw", "CRITICAL", f"BRAKE!  {v.label.upper()} {v.distance:.1f} m  TTC {v.ttc:.1f} s"))
        elif v.ttc is not None and v.ttc < cfg["ttc_warning_s"]:
            out.append(Alert("fcw", "WARNING", f"COLLISION RISK  {v.label} {v.distance:.1f} m  TTC {v.ttc:.1f} s"))
        elif v.distance < cfg["close_vehicle_m"]:
            out.append(Alert("fcw", "WARNING", f"TOO CLOSE  {v.label} {v.distance:.1f} m"))

    if lanes is not None and lanes.departure != "NONE":
        out.append(Alert("ldw", "WARNING", f"LANE DEPARTURE {lanes.departure}"))
    return out


class AlertManager:
    """Holds each alert for `hold_s` after its condition clears so the display does not flicker."""

    def __init__(self, hold_s: float = 0.8):
        self.hold_s = hold_s
        self._active: Dict[str, tuple] = {}  # key -> (Alert, last_seen)

    def update(self, alerts: List[Alert], now: Optional[float] = None) -> List[Alert]:
        now = time.perf_counter() if now is None else now
        for a in alerts:
            self._active[a.key] = (a, now)
        self._active = {k: v for k, v in self._active.items() if now - v[1] <= self.hold_s}
        return sorted((v[0] for v in self._active.values()), key=lambda a: LEVEL_RANK[a.level])
