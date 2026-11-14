"""
Custom Automotive Gauge Widgets (Speedometer & G-Force Meter).
Rendered with antialiased QPainter arc gradients.
"""

import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class SpeedometerWidget(QWidget):
    def __init__(self, max_speed: float = 160.0, parent=None):
        super().__init__(parent)
        self.max_speed = max_speed
        self.current_speed = 0.0
        self.setMinimumSize(180, 180)

    def set_speed(self, speed_kmh: float) -> None:
        self.current_speed = max(0.0, min(self.max_speed, speed_kmh))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h)
        cx, cy = w / 2, h / 2
        radius = side * 0.42

        # Outer Track Arc
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        pen_track = QPen(QColor(33, 40, 50), 10, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_track)
        # Arc from 225 deg to -45 deg (270 degree span)
        painter.drawArc(rect, int(-45 * 16), int(270 * 16))

        # Active Speed Arc
        fraction = self.current_speed / self.max_speed
        span_angle = -270 * fraction
        pen_speed = QPen(QColor(0, 210, 255), 10, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_speed)
        painter.drawArc(rect, int(225 * 16), int(span_angle * 16))

        # Digital Center Speed
        font_val = QFont()
        font_val.setPointSize(int(side * 0.16))
        font_val.setBold(True)
        painter.setFont(font_val)
        painter.setPen(QColor(240, 246, 252))
        painter.drawText(
            QRectF(cx - radius, cy - radius * 0.35, radius * 2, radius * 0.7),
            Qt.AlignCenter,
            f"{self.current_speed:3.0f}",
        )

        # Unit Label
        font_unit = QFont()
        font_unit.setPointSize(int(side * 0.07))
        font_unit.setBold(True)
        painter.setFont(font_unit)
        painter.setPen(QColor(139, 148, 158))
        painter.drawText(
            QRectF(cx - radius, cy + radius * 0.25, radius * 2, radius * 0.4),
            Qt.AlignCenter,
            "KM/H",
        )


class GForceMeterWidget(QWidget):
    def __init__(self, max_g: float = 4.0, threshold_g: float = 2.2, parent=None):
        super().__init__(parent)
        self.max_g = max_g
        self.threshold_g = threshold_g
        self.current_g = 1.0
        self.setMinimumSize(180, 180)

    def set_g_force(self, g_val: float) -> None:
        self.current_g = max(0.0, min(self.max_g, g_val))
        self.update()

    def set_threshold(self, threshold_g: float) -> None:
        self.threshold_g = threshold_g
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h)
        cx, cy = w / 2, h / 2
        radius = side * 0.42

        # Track
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        pen_track = QPen(QColor(33, 40, 50), 10, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_track)
        painter.drawArc(rect, int(-45 * 16), int(270 * 16))

        # Dynamic color based on threshold
        color = QColor(0, 230, 118)
        if self.current_g >= self.threshold_g:
            color = QColor(255, 51, 75)
        elif self.current_g >= self.threshold_g * 0.8:
            color = QColor(255, 183, 3)

        fraction = self.current_g / self.max_g
        span_angle = -270 * fraction
        pen_active = QPen(color, 10, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_active)
        painter.drawArc(rect, int(225 * 16), int(span_angle * 16))

        # Value
        font_val = QFont()
        font_val.setPointSize(int(side * 0.15))
        font_val.setBold(True)
        painter.setFont(font_val)
        painter.setPen(color)
        painter.drawText(
            QRectF(cx - radius, cy - radius * 0.35, radius * 2, radius * 0.7),
            Qt.AlignCenter,
            f"{self.current_g:3.2f}",
        )

        # Label
        font_unit = QFont()
        font_unit.setPointSize(int(side * 0.07))
        font_unit.setBold(True)
        painter.setFont(font_unit)
        painter.setPen(QColor(139, 148, 158))
        painter.drawText(
            QRectF(cx - radius, cy + radius * 0.25, radius * 2, radius * 0.4),
            Qt.AlignCenter,
            f"G-FORCE (TH: {self.threshold_g:.1f}g)",
        )
