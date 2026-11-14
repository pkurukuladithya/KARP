"""
Automotive Vector Map & GPS Location Widget.
Draws vehicle coordinates, heading vector, historical track trail, and fix status.
Operates fully offline without requiring cloud tile downloads.
"""

import math
from collections import deque
from typing import Deque, Optional, Tuple
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


class MapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.latitude: float = 0.0
        self.longitude: float = 0.0
        self.altitude_m: float = 0.0
        self.speed_kmh: float = 0.0
        self.heading_deg: float = 0.0
        self.satellites: int = 0
        self.fix_quality: int = 0
        self.is_simulated: bool = False

        # Store recent (lat, lon) coordinates for drawing vehicle path trail
        self.track_history: Deque[Tuple[float, float]] = deque(maxlen=200)

        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #070A0F;")

    def update_gps(
        self,
        lat: float,
        lon: float,
        alt: float,
        speed: float,
        heading: float,
        sats: int,
        fix_quality: int,
        is_simulated: bool,
    ) -> None:
        self.latitude = lat
        self.longitude = lon
        self.altitude_m = alt
        self.speed_kmh = speed
        self.heading_deg = heading
        self.satellites = sats
        self.fix_quality = fix_quality
        self.is_simulated = is_simulated

        if fix_quality > 0 or is_simulated:
            if not self.track_history or (abs(lat - self.track_history[-1][0]) > 1e-6 or abs(lon - self.track_history[-1][1]) > 1e-6):
                self.track_history.append((lat, lon))

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(7, 10, 15))

        # Check fix status
        has_fix = (self.fix_quality > 0) or self.is_simulated

        # Draw coordinate grid
        self._draw_grid(painter, w, h)

        if has_fix and self.track_history:
            self._draw_track_and_vehicle(painter, w, h)
        else:
            self._draw_no_fix(painter, w, h)

        # Draw HUD overlays: Status Badge, Coordinates, Compass
        self._draw_badges_and_stats(painter, w, h)

    def _draw_grid(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QPen(QColor(20, 27, 36), 1, Qt.DotLine))
        step = 60
        for x in range(step, w, step):
            painter.drawLine(x, 0, x, h)
        for y in range(step, h, step):
            painter.drawLine(0, y, w, y)

    def _draw_track_and_vehicle(self, painter: QPainter, w: int, h: int) -> None:
        cx, cy = w / 2, h / 2

        # Scale coordinates relative to current position
        scale = 35000.0  # Pixels per degree lat/lon

        # Draw Track Trail
        points = []
        for lat, lon in self.track_history:
            d_lon = (lon - self.longitude) * math.cos(math.radians(self.latitude))
            d_lat = lat - self.latitude
            px = cx + d_lon * scale
            py = cy - d_lat * scale
            points.append(QPointF(px, py))

        if len(points) >= 2:
            trail_color = QColor(0, 210, 255, 140) if self.is_simulated else QColor(0, 230, 118, 160)
            painter.setPen(QPen(trail_color, 3, Qt.SolidLine, Qt.RoundCap))
            painter.drawPolyline(QPolygonF(points))

        # Draw Vehicle Position & Heading Indicator
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.heading_deg)

        # Vehicle Arrow Triangle
        arrow = QPolygonF([
            QPointF(0, -18),
            QPointF(11, 14),
            QPointF(0, 8),
            QPointF(-11, 14),
        ])
        painter.setPen(QPen(QColor(240, 246, 252), 2))
        painter.setBrush(QColor(0, 210, 255) if self.is_simulated else QColor(0, 230, 118))
        painter.drawPolygon(arrow)
        painter.restore()

        # Radar pulse ring around vehicle
        painter.setPen(QPen(QColor(0, 210, 255, 60), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), 35, 35)

    def _draw_no_fix(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QColor(255, 183, 3))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignCenter,
            "ACQUIRING SATELLITE FIX...\nANTENNA REQUIRES OPEN SKY VIEW",
        )

    def _draw_badges_and_stats(self, painter: QPainter, w: int, h: int) -> None:
        # Top-left Status Badge
        badge_rect = QRectF(12, 12, 280, 32)
        painter.fillRect(badge_rect, QColor(16, 22, 30, 220))

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        if self.is_simulated:
            painter.setPen(QColor(0, 210, 255))
            status_str = f"SIMULATION MODE (GPS TRACK SYNTH)"
        elif self.fix_quality > 0:
            painter.setPen(QColor(0, 230, 118))
            status_str = f"LIVE FIX: {self.satellites} SATS (QUALITY: {self.fix_quality})"
        else:
            painter.setPen(QColor(255, 51, 75))
            status_str = f"NO FIX: {self.satellites} SATS DETECTED"

        painter.drawText(badge_rect.adjusted(12, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, status_str)

        # Bottom-left Coordinates Card
        coord_rect = QRectF(12, h - 85, 320, 72)
        painter.fillRect(coord_rect, QColor(16, 22, 30, 220))
        painter.setPen(QPen(QColor(48, 54, 61), 1))
        painter.drawRect(coord_rect)

        painter.setPen(QColor(240, 246, 252))
        font_data = QFont()
        font_data.setPointSize(9)
        painter.setFont(font_data)

        lat_str = f"LAT: {self.latitude:10.6f}°"
        lon_str = f"LON: {self.longitude:10.6f}°"
        alt_str = f"ALT: {self.altitude_m:5.1f} m"
        spd_str = f"SPD: {self.speed_kmh:5.1f} km/h"
        hdg_str = f"HDG: {self.heading_deg:4.1f}°"

        painter.drawText(22, h - 63, f"{lat_str}   {lon_str}")
        painter.drawText(22, h - 43, f"{alt_str}   {spd_str}   {hdg_str}")
        painter.setPen(QColor(139, 148, 158))
        painter.drawText(22, h - 23, "Vector Navigation Engine | WGS-84 Datum")
