"""
GPS Telemetry & Track Processor.
Calculates geographic trajectory, heading angles, and satellite fix metrics.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ProcessedGpsState:
    latitude: float
    longitude: float
    altitude_m: float
    speed_kmh: float
    heading_deg: float
    satellites: int
    fix_quality: int
    is_valid: bool
    is_simulated: bool


class GpsProcessor:
    def __init__(self):
        self._prev_lat: Optional[float] = None
        self._prev_lon: Optional[float] = None
        self._last_heading: float = 0.0

    def process(
        self,
        lat: float,
        lon: float,
        alt: float = 0.0,
        speed_kmh: float = 0.0,
        heading_deg: float = 0.0,
        satellites: int = 0,
        fix_quality: int = 0,
        is_simulated: bool = False,
    ) -> ProcessedGpsState:
        # Check validity
        is_valid = (fix_quality > 0 or is_simulated) and (-90.0 <= lat <= 90.0) and (-180.0 <= lon <= 180.0)

        # Compute heading if not provided by GPS chip and position changed
        if is_valid and self._prev_lat is not None and self._prev_lon is not None:
            d_lat = lat - self._prev_lat
            d_lon = (lon - self._prev_lon) * math.cos(math.radians(lat))
            dist = math.sqrt(d_lat * d_lat + d_lon * d_lon)
            if dist > 1e-6 and heading_deg == 0.0:
                angle_rad = math.atan2(d_lon, d_lat)
                self._last_heading = (math.degrees(angle_rad) + 360.0) % 360.0
            elif heading_deg != 0.0:
                self._last_heading = heading_deg
        elif heading_deg != 0.0:
            self._last_heading = heading_deg

        if is_valid:
            self._prev_lat = lat
            self._prev_lon = lon

        return ProcessedGpsState(
            latitude=lat,
            longitude=lon,
            altitude_m=alt,
            speed_kmh=speed_kmh,
            heading_deg=self._last_heading,
            satellites=satellites,
            fix_quality=fix_quality,
            is_valid=is_valid,
            is_simulated=is_simulated,
        )
