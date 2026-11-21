"""
Single source of truth for what the UI may show about the vehicle.

Rule: only real sensor values are shown. Nothing is simulated.

  ESP32 offline      -> "ESP32 NOT CONNECTED", speed "--", no position, no road state
  GPS no NMEA data   -> "GPS NO DATA" (module wiring/power), speed "--"
  GPS searching      -> "GPS CONNECTING...", speed "--"
  GPS fix            -> real speed, position, heading; the MPU6050 confirms standstill
                        (GPS drift at standstill must not show as a few km/h)
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

GPS_ESP_OFFLINE = "ESP_OFFLINE"
GPS_NO_DATA = "NO_DATA"
GPS_CONNECTING = "CONNECTING"
GPS_FIX = "FIX"

# Standstill check with the MPU6050: a parked car has almost no vibration, while
# NEO-6M position drift can report a few km/h. Below GPS_DRIFT_KMH we only believe
# the GPS speed if the MPU also feels the car moving.
STILL_VIBRATION_G = 0.03
GPS_DRIFT_KMH = 8.0

# Colours (BGR)
GREEN = (0, 230, 80)
ORANGE = (0, 165, 255)
RED = (0, 60, 255)
GREY = (150, 150, 150)


@dataclass
class VehicleState:
    esp_online: bool = False
    esp_link: str = "NO PORT"
    gps: str = GPS_ESP_OFFLINE
    satellites: int = 0
    speed_kmh: Optional[float] = None  # None = unknown -> display "--"
    moving: Optional[bool] = None  # None = unknown
    motion_source: str = ""  # which sensor decided moving/stationary
    lat: Optional[float] = None  # current real fix only
    lon: Optional[float] = None
    heading_deg: Optional[float] = None
    altitude_m: Optional[float] = None
    last_lat: Optional[float] = None  # last real fix (kept when the fix is lost)
    last_lon: Optional[float] = None
    last_fix_age_s: Optional[float] = None
    mpu_ok: bool = False
    road: Optional[str] = None  # None = unknown
    pothole: bool = False

    @property
    def has_fix(self) -> bool:
        return self.gps == GPS_FIX

    @property
    def speed_text(self) -> str:
        return "--" if self.speed_kmh is None else f"{self.speed_kmh:.0f}"

    @property
    def gps_text(self) -> str:
        if self.gps == GPS_ESP_OFFLINE:
            return "ESP32 NOT CONNECTED"
        if self.gps == GPS_NO_DATA:
            return "GPS NO DATA"
        if self.gps == GPS_CONNECTING:
            return f"GPS CONNECTING... ({self.satellites} SATS)" if self.satellites else "GPS CONNECTING..."
        return f"GPS FIX ({self.satellites} SATS)"

    @property
    def gps_color(self) -> Tuple[int, int, int]:
        return {GPS_FIX: GREEN, GPS_CONNECTING: ORANGE}.get(self.gps, RED)

    @property
    def speed_status(self) -> str:
        """Short line under the speed number explaining where it comes from."""
        if self.gps == GPS_ESP_OFFLINE:
            return "NO ESP32"
        if self.gps == GPS_NO_DATA:
            return "NO GPS DATA"
        if self.gps == GPS_CONNECTING:
            return "GPS CONNECTING"
        return "STATIONARY" if self.moving is False else "GPS"

    @property
    def road_text(self) -> str:
        if not self.esp_online:
            return "ESP32 OFF"
        if not self.mpu_ok:
            return "MPU ERROR"
        return (self.road or "UNKNOWN").upper()

    @property
    def road_color(self) -> Tuple[int, int, int]:
        if not self.esp_online or not self.mpu_ok:
            return GREY
        return {"SMOOTH": GREEN, "MODERATE": (0, 215, 255), "ROUGH": RED}.get(self.road_text, (200, 200, 200))

    def summary(self) -> str:
        spd = "--" if self.speed_kmh is None else f"{self.speed_kmh:.1f} km/h"
        mv = "?" if self.moving is None else ("MOVING" if self.moving else "STATIONARY")
        return f"{self.gps_text} | speed {spd} ({mv}{', ' + self.motion_source if self.motion_source else ''}) | road {self.road_text}"


class VehicleStateEstimator:
    """Turns raw ESP32 telemetry (Esp32Client.get_telemetry()) into a VehicleState."""

    def __init__(self) -> None:
        self._last_fix: Optional[Tuple[float, float]] = None
        self._last_fix_t: Optional[float] = None
        self._last_heading: Optional[float] = None

    def update(self, t: Dict[str, Any], now: Optional[float] = None) -> VehicleState:
        now = time.perf_counter() if now is None else now
        vs = VehicleState()
        if self._last_fix is not None:
            vs.last_lat, vs.last_lon = self._last_fix
            vs.last_fix_age_s = now - self._last_fix_t

        if not t.get("connected"):
            vs.esp_link = str(t.get("link") or "NO PORT")
            return vs  # everything unknown

        vs.esp_online = True
        vs.esp_link = "ONLINE"
        vs.satellites = int(t.get("satellites") or 0)
        vs.mpu_ok = bool(t.get("mpu_connected"))
        road = t.get("road")
        vs.road = str(road) if vs.mpu_ok and road and road not in ("SENSOR_ERROR", "DISCONNECTED") else None
        vs.pothole = bool(t.get("pothole"))

        if t.get("gps_valid") and t.get("lat") is not None and t.get("lon") is not None:
            vs.gps = GPS_FIX
        elif t.get("gps_connected"):
            vs.gps = GPS_CONNECTING
        else:
            vs.gps = GPS_NO_DATA

        if vs.gps != GPS_FIX:
            return vs  # no speed / position without a fix

        vs.lat, vs.lon = float(t["lat"]), float(t["lon"])
        vs.altitude_m = float(t.get("altitude_m") or 0.0)
        self._last_fix, self._last_fix_t = (vs.lat, vs.lon), now
        vs.last_lat, vs.last_lon, vs.last_fix_age_s = vs.lat, vs.lon, 0.0

        raw = float(t.get("raw_speed_kmh") or 0.0)
        fw_moving = bool(t.get("vehicle_moving"))
        mpu_still = vs.mpu_ok and float(t.get("vibration") or 0.0) < STILL_VIBRATION_G

        if mpu_still and raw < GPS_DRIFT_KMH:
            vs.moving, vs.speed_kmh, vs.motion_source = False, 0.0, "MPU"
        elif not fw_moving:
            vs.moving, vs.speed_kmh, vs.motion_source = False, 0.0, "GPS+MPU" if vs.mpu_ok else "GPS"
        else:
            vs.moving, vs.speed_kmh, vs.motion_source = True, raw, "GPS+MPU" if vs.mpu_ok else "GPS"

        # GPS course is meaningless while standing still: keep the last real heading
        if vs.moving:
            self._last_heading = float(t.get("heading_deg") or 0.0)
        vs.heading_deg = self._last_heading
        return vs
