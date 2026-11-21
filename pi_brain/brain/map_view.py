"""
Automotive OpenStreetMap (OSM) Navigation & Radar Canvas for KARP Pi Brain (480x320 LCD).

Features:
  - Real OpenStreetMap (OSM) raster tile rendering at street-level zoom (Zoom 15-16).
  - Background asynchronous tile downloading and persistent local disk caching.
  - Zero-lag architecture: display loop never blocks on network requests.
  - Sleek automotive dark-theme filter for night/cabin driving (avoids bright screen glare).
  - Vehicle marker (cyan arrowhead ▲) locked to exact road coordinates and rotated by heading.
  - Real GPS breadcrumb trajectory trail rendered on top of actual street maps.
  - High-visibility automotive digital speedometer and telemetry cards.
  - Full ADAS collision / lane departure alert pass-through.
  - Split-view rendering (ADAS Vision + OSM Map side-by-side).
"""

from __future__ import annotations
import math
import os
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

from .alerts import Alert
from .hud import draw_alerts, FONT

BASE_DIR = Path(__file__).resolve().parents[1]
MAP_CACHE_DIR = BASE_DIR / "data" / "map_cache"


def lat_lon_to_tile(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[float, float]:
    """Converts (lat, lon) in degrees to fractional Slippy Map tile coordinates."""
    n = 2.0 ** zoom
    x_tile = (lon_deg + 180.0) / 360.0 * n
    lat_rad = math.radians(min(85.0511, max(-85.0511, lat_deg)))
    y_tile = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n
    return x_tile, y_tile


class OSMTileManager:
    """Manages downloading, local disk caching, in-memory caching, and dark styling of OSM tiles."""

    def __init__(self, cache_dir: Path = MAP_CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[Tuple[int, int, int, bool], np.ndarray] = {}
        self._max_mem_tiles = 64
        self._lock = threading.Lock()
        self._download_queue: Deque[Tuple[int, int, int]] = deque()
        self._queued_set: Set[Tuple[int, int, int]] = set()

        self._running = True
        self._worker_thread = threading.Thread(target=self._download_worker, daemon=True, name="OSMTileDownloader")
        self._worker_thread.start()

    def get_tile(self, zoom: int, x: int, y: int, dark_mode: bool = True) -> np.ndarray:
        """Returns the 256x256 tile image. Non-blocking: returns fallback grid if downloading."""
        key = (zoom, x, y, dark_mode)
        with self._lock:
            if key in self._memory_cache:
                return self._memory_cache[key]

        tile_path = self.cache_dir / str(zoom) / f"{x}_{y}.png"
        if tile_path.is_file():
            raw = cv2.imread(str(tile_path))
            if raw is not None and raw.shape == (256, 256, 3):
                tile = self._style_tile(raw, dark_mode)
                with self._lock:
                    if len(self._memory_cache) > self._max_mem_tiles:
                        self._memory_cache.clear()
                    self._memory_cache[key] = tile
                return tile

        # Not yet on disk: enqueue background download and return instant placeholder
        with self._lock:
            coord = (zoom, x, y)
            if coord not in self._queued_set:
                self._queued_set.add(coord)
                self._download_queue.append(coord)

        return self._create_placeholder_tile(zoom, x, y)

    def _style_tile(self, tile: np.ndarray, dark_mode: bool) -> np.ndarray:
        if not dark_mode:
            return tile

        # High-contrast automotive dark theme for OpenStreetMap
        gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
        inv = 255 - gray

        # Slate / navy dark background
        dark = np.empty_like(tile)
        dark[..., 0] = np.clip(inv * 0.38 + 22, 0, 255).astype(np.uint8)  # Blue/Navy
        dark[..., 1] = np.clip(inv * 0.28 + 16, 0, 255).astype(np.uint8)  # Green
        dark[..., 2] = np.clip(inv * 0.20 + 12, 0, 255).astype(np.uint8)  # Red

        # Preserve / boost road lines and street labels
        roads = (gray > 195) | (gray < 70)
        dark[roads] = np.clip(dark[roads].astype(np.int16) + 45, 0, 255).astype(np.uint8)
        return dark

    def _create_placeholder_tile(self, zoom: int, x: int, y: int) -> np.ndarray:
        """Instant dark grid tile shown while download is in flight."""
        tile = np.full((256, 256, 3), (20, 16, 12), dtype=np.uint8)
        cv2.rectangle(tile, (0, 0), (255, 255), (38, 48, 58), 1)
        for offset in (64, 128, 192):
            cv2.line(tile, (offset, 0), (offset, 256), (28, 35, 42), 1)
            cv2.line(tile, (0, offset), (256, offset), (28, 35, 42), 1)
        cv2.putText(tile, f"OSM {zoom}/{x}/{y}", (12, 130), FONT, 0.32, (60, 75, 90), 1, cv2.LINE_AA)
        return tile

    def _download_worker(self) -> None:
        """Background thread downloading OSM tiles without blocking the ADAS."""
        while self._running:
            coord = None
            with self._lock:
                if self._download_queue:
                    coord = self._download_queue.popleft()
                    self._queued_set.discard(coord)
            if coord is None:
                time.sleep(0.1)
                continue

            z, x, y = coord
            tile_dir = self.cache_dir / str(z)
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile_path = tile_dir / f"{x}_{y}.png"
            if tile_path.is_file():
                continue

            url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            req = urllib.request.Request(url, headers={"User-Agent": "KARP-ADAS-PiBrain/1.0 (https://github.com/your-org/KARP)"})
            try:
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = resp.read()
                img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                if img is not None and img.shape == (256, 256, 3):
                    cv2.imwrite(str(tile_path), img)
                time.sleep(0.12)  # Respect OpenStreetMap tile server rate policy
            except Exception:
                time.sleep(0.5)

    def stop(self) -> None:
        self._running = False


class MapView:
    def __init__(
        self,
        width: int = 480,
        height: int = 320,
        lat: float = 6.9271,
        lon: float = 79.8612,
        zoom: int = 16,
        base_speed: float = 48.0,
        dark_mode: bool = True,
    ):
        self.w = int(width)
        self.h = int(height)
        self.lat = float(lat)
        self.lon = float(lon)
        self.zoom = int(zoom)
        self.dark_mode = bool(dark_mode)
        self.base_speed = float(base_speed)
        self.current_speed = self.base_speed
        self.heading_deg = 42.0
        self.altitude_m = 18.5
        self.satellites = 9
        self.has_fix = True
        self.road_condition = "SMOOTH"
        self.pothole_detected = False

        self._t_last = time.perf_counter()
        self._trail_gps: Deque[Tuple[float, float]] = deque(maxlen=40)
        self._tile_mgr = OSMTileManager()

    def update_telemetry(
        self,
        speed_kmh: Optional[float] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        heading: Optional[float] = None,
        satellites: Optional[int] = None,
        has_fix: Optional[bool] = None,
        altitude: Optional[float] = None,
        road: Optional[str] = None,
        pothole: bool = False,
        sim_movement: bool = True,
    ) -> float:
        """Updates vehicle state from real GPS/ESP32; simulates realistic motion if disconnected."""
        now = time.perf_counter()
        dt = max(0.001, min(0.2, now - self._t_last))
        self._t_last = now

        if satellites is not None:
            self.satellites = int(satellites)
        if has_fix is not None:
            self.has_fix = bool(has_fix)
        if altitude is not None:
            self.altitude_m = float(altitude)
        if road is not None:
            self.road_condition = str(road)
        self.pothole_detected = bool(pothole)

        if speed_kmh is not None:
            self.current_speed = float(speed_kmh)
        elif sim_movement:
            # Subtle driving variation around base_speed (e.g. 47.4 to 48.8 km/h)
            self.current_speed = self.base_speed + 1.2 * math.sin(now * 0.4) + 0.4 * math.cos(now * 0.9)

        if heading is not None:
            self.heading_deg = float(heading)
        elif sim_movement and self.current_speed > 2.0:
            # Gentle realistic steering curvature along the road
            self.heading_deg = (self.heading_deg + 0.6 * math.sin(now * 0.18) * dt * 8.0) % 360.0

        if lat is not None and lon is not None:
            self.lat, self.lon = float(lat), float(lon)
        elif sim_movement and self.current_speed > 1.0:
            speed_ms = self.current_speed / 3.6
            dist_m = speed_ms * dt
            rad = math.radians(self.heading_deg)
            self.lat += (dist_m * math.cos(rad)) / 111111.0
            self.lon += (dist_m * math.sin(rad)) / (111111.0 * math.cos(math.radians(self.lat)))

        self._trail_gps.append((self.lat, self.lon))
        return self.current_speed

    def render(self, speed_kmh: float, alerts: List[Alert], mode_name: str = "MAP") -> np.ndarray:
        """Renders the full 480x320 OpenStreetMap navigation canvas."""
        w, h = self.w, self.h

        # 1. Generate stitched OpenStreetMap canvas centered on the vehicle
        canvas = self._render_osm_background(w, h)

        # 2. Draw GPS trajectory breadcrumb trail over real streets
        self._draw_trajectory_trail(canvas, w, h)

        # 3. Draw Vehicle Position & Heading Marker (Cyan Arrowhead ▲)
        self._draw_vehicle_marker(canvas, w // 2, h // 2)

        # 4. Automotive Digital Speedometer Card (Left Panel)
        self._draw_speedometer(canvas, 10, 36, speed_kmh)

        # 5. Telemetry Cards (GPS Coordinates, Heading, Satellites)
        self._draw_telemetry_info(canvas, 10, 168)

        # 6. Top Status Header & Mode Switcher Pill
        self._draw_top_bar(canvas, mode_name)

        # 7. Bottom Coordinates Bar
        self._draw_bottom_bar(canvas)

        # 8. Safety Alert Banners (flashes on top if collision / lane departure occurs)
        if alerts:
            draw_alerts(canvas, alerts)

        return canvas

    def render_split(self, vision_frame: np.ndarray, speed_kmh: float, alerts: List[Alert]) -> np.ndarray:
        """Renders 50/50 Split View: Left half = ADAS Vision, Right half = OSM Navigation Map."""
        w, h = self.w, self.h
        half_w = w // 2

        # Resize camera vision frame to fit left half
        left_img = cv2.resize(vision_frame, (half_w, h), interpolation=cv2.INTER_LINEAR)

        # Render OSM map on right half
        right_img = self._render_osm_background(half_w, h)
        self._draw_trajectory_trail(right_img, half_w, h)
        self._draw_vehicle_marker(right_img, half_w // 2, int(h * 0.46))
        self._draw_speedometer(right_img, 8, int(h * 0.65), speed_kmh, compact=True)

        # Combine halves
        canvas = np.hstack([left_img, right_img])

        # Vertical divider line
        cv2.line(canvas, (half_w, 0), (half_w, h), (55, 75, 95), 2)

        # Top Bar
        bar_h = 22
        canvas[:bar_h] = (canvas[:bar_h] * 0.35).astype(np.uint8)
        cv2.putText(canvas, f"VISION (L) | OSM MAP (R) | {speed_kmh:.0f} KM/H", (6, 16), FONT, 0.42, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(canvas, "[CLICK TO SWITCH]", (w - 140, 16), FONT, 0.36, (0, 220, 255), 1, cv2.LINE_AA)

        if alerts:
            draw_alerts(canvas, alerts)

        return canvas

    # ------------------------------------------------------------- OSM Stitched Rendering
    def _render_osm_background(self, target_w: int, target_h: int) -> np.ndarray:
        """Fetches a 3x3 grid of 256x256 OSM tiles and crops a window centered on the vehicle."""
        z = self.zoom
        xf, yf = lat_lon_to_tile(self.lat, self.lon, z)
        xi, yi = int(math.floor(xf)), int(math.floor(yf))

        # Vehicle subpixel offset within center tile
        px = (xf - xi) * 256.0
        py = (yf - yi) * 256.0

        # Construct 3x3 composite (768x768 pixels)
        grid_3x3 = np.empty((768, 768, 3), dtype=np.uint8)
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                tile = self._tile_mgr.get_tile(z, xi + dx, yi + dy, dark_mode=self.dark_mode)
                row = (dy + 1) * 256
                col = (dx + 1) * 256
                grid_3x3[row : row + 256, col : col + 256] = tile

        # Center vehicle exactly at (target_w // 2, target_h // 2)
        veh_grid_x = 256.0 + px
        veh_grid_y = 256.0 + py

        crop_x0 = int(round(veh_grid_x - (target_w / 2.0)))
        crop_y0 = int(round(veh_grid_y - (target_h / 2.0)))

        # Safeguard crop bounds
        crop_x0 = max(0, min(768 - target_w, crop_x0))
        crop_y0 = max(0, min(768 - target_h, crop_y0))

        return grid_3x3[crop_y0 : crop_y0 + target_h, crop_x0 : crop_x0 + target_w].copy()

    def _draw_trajectory_trail(self, img: np.ndarray, target_w: int, target_h: int) -> None:
        """Projects recent GPS coordinates onto the canvas as a glowing trajectory trail."""
        if len(self._trail_gps) < 2:
            return

        z = self.zoom
        curr_xf, curr_yf = lat_lon_to_tile(self.lat, self.lon, z)
        cx, cy = target_w // 2, target_h // 2

        pts = []
        for t_lat, t_lon in self._trail_gps:
            txf, tyf = lat_lon_to_tile(t_lat, t_lon, z)
            dx_px = (txf - curr_xf) * 256.0
            dy_px = (tyf - curr_yf) * 256.0
            px = int(cx + dx_px)
            py = int(cy + dy_px)
            if 0 <= px < target_w and 0 <= py < target_h:
                pts.append((px, py))

        if len(pts) >= 2:
            pts_arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(img, [pts_arr], False, (0, 220, 255), 2, cv2.LINE_AA)

    def _draw_vehicle_marker(self, img: np.ndarray, cx: int, cy: int) -> None:
        """Draws the glowing automotive vehicle marker (▲) oriented by heading."""
        # Rotating arrowhead
        rad = math.radians(self.heading_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        base_pts = [
            (0, -15),   # Top nose
            (-10, 11),  # Bottom-left
            (0, 5),     # Inset notch
            (10, 11),   # Bottom-right
        ]

        rotated_pts = []
        for x, y in base_pts:
            rx = int(cx + (x * cos_a - y * sin_a))
            ry = int(cy + (x * sin_a + y * cos_a))
            rotated_pts.append([rx, ry])

        poly = np.array(rotated_pts, dtype=np.int32)
        cv2.circle(img, (cx, cy), 16, (40, 70, 90), 1, cv2.LINE_AA)
        cv2.fillPoly(img, [poly], (255, 215, 0))  # Cyan body
        cv2.polylines(img, [poly], True, (255, 255, 255), 1, cv2.LINE_AA)  # White border
        cv2.circle(img, (cx, cy), 2, (0, 255, 255), -1)

    def _draw_speedometer(self, img: np.ndarray, x: int, y: int, speed: float, compact: bool = False) -> None:
        bw, bh = (175, 120) if not compact else (135, 90)
        roi = img[y : y + bh, x : x + bw]
        over = np.full_like(roi, (22, 18, 14))
        cv2.addWeighted(over, 0.82, roi, 0.18, 0, dst=roi)
        cv2.rectangle(img, (x, y), (x + bw, y + bh), (60, 75, 90), 1)

        cv2.putText(img, "GROUND SPEED", (x + 8, y + 16), FONT, 0.35, (150, 170, 190), 1, cv2.LINE_AA)

        spd_str = f"{max(0.0, speed):.0f}"
        num_scale = 1.35 if not compact else 1.05
        (tw, th), _ = cv2.getTextSize(spd_str, FONT, num_scale, 2)
        cv2.putText(img, spd_str, (x + 12, y + 20 + th + 6), FONT, num_scale, (0, 230, 255), 2, cv2.LINE_AA)
        cv2.putText(img, "KM/H", (x + 18 + tw, y + 20 + th - 2), FONT, 0.45, (0, 200, 230), 1, cv2.LINE_AA)

        bar_x = x + 10
        bar_y = y + bh - 16
        bar_w = bw - 20
        cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_w, bar_y + 6), (40, 45, 50), -1)
        pct = min(1.0, max(0.0, speed / 120.0))
        fill_w = int(bar_w * pct)
        bar_color = (0, 215, 255) if speed < 80 else ((0, 160, 255) if speed < 100 else (0, 0, 255))
        if fill_w > 0:
            cv2.rectangle(img, (bar_x, bar_y), (bar_x + fill_w, bar_y + 6), bar_color, -1)

    def _draw_telemetry_info(self, img: np.ndarray, x: int, y: int) -> None:
        bw, bh = 175, 110
        roi = img[y : y + bh, x : x + bw]
        over = np.full_like(roi, (22, 18, 14))
        cv2.addWeighted(over, 0.82, roi, 0.18, 0, dst=roi)
        cv2.rectangle(img, (x, y), (x + bw, y + bh), (60, 75, 90), 1)

        cv2.putText(img, "TELEMETRY & ROAD", (x + 8, y + 16), FONT, 0.35, (150, 170, 190), 1, cv2.LINE_AA)

        road_txt = f"ROAD: {self.road_condition}" if not self.pothole_detected else "! POTHOLE ALERT !"
        road_col = (0, 0, 255) if self.pothole_detected else ((0, 230, 80) if self.road_condition == "SMOOTH" else ((0, 210, 255) if self.road_condition == "MODERATE" else (0, 80, 255)))

        items = [
            (f"LAT:  {self.lat:.4f} N", (200, 220, 235)),
            (f"LON:  {self.lon:.4f} E", (200, 220, 235)),
            (f"HDG:  {self.heading_deg:03.0f} deg ({self._compass_heading()})", (200, 220, 235)),
            (road_txt, road_col),
        ]
        for idx, (text, col) in enumerate(items):
            cv2.putText(img, text, (x + 10, y + 36 + idx * 18), FONT, 0.36, col, 1, cv2.LINE_AA)

    def _draw_top_bar(self, img: np.ndarray, mode_name: str) -> None:
        bar_h = 24
        img[:bar_h] = (img[:bar_h] * 0.35).astype(np.uint8)

        # GPS Fix indicator
        fix_text = f"GPS: 3D FIX ({self.satellites} SATS)" if self.has_fix else "GPS: SEARCHING..."
        fix_color = (0, 230, 80) if self.has_fix else (0, 100, 255)
        cv2.circle(img, (12, 12), 4, fix_color, -1)
        cv2.putText(img, fix_text, (22, 16), FONT, 0.38, (220, 230, 240), 1, cv2.LINE_AA)

        # Mode Switcher Pill
        mode_pill = f"[{mode_name.upper()} | CLICK TO SWITCH]"
        (mw, _), _ = cv2.getTextSize(mode_pill, FONT, 0.38, 1)
        cv2.putText(img, mode_pill, (self.w - mw - 10, 16), FONT, 0.38, (0, 215, 255), 1, cv2.LINE_AA)

    def _draw_bottom_bar(self, img: np.ndarray) -> None:
        bar_h = 22
        y0 = self.h - bar_h
        img[y0:] = (img[y0:] * 0.35).astype(np.uint8)
        foot = f"OpenStreetMap (ODbL) | COORD {self.lat:.5f}, {self.lon:.5f} | ZOOM {self.zoom}"
        cv2.putText(img, foot, (10, self.h - 6), FONT, 0.34, (150, 170, 190), 1, cv2.LINE_AA)

    def _compass_heading(self) -> str:
        pts = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        idx = int((self.heading_deg + 22.5) / 45.0) % 8
        return pts[idx]
