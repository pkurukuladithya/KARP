"""
Real-Time Accelerometer Waveform Chart Widget.
Smooth rolling oscilloscope chart for Ax, Ay, Az and Magnitude with threshold line.
"""

from collections import deque
from typing import Deque, List, Tuple
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


class AccelerometerChartWidget(QWidget):
    def __init__(self, buffer_size: int = 150, threshold_g: float = 2.2, parent=None):
        super().__init__(parent)
        self.buffer_size = buffer_size
        self.threshold_g = threshold_g

        self.history_x: Deque[float] = deque([0.0] * buffer_size, maxlen=buffer_size)
        self.history_y: Deque[float] = deque([0.0] * buffer_size, maxlen=buffer_size)
        self.history_z: Deque[float] = deque([1.0] * buffer_size, maxlen=buffer_size)
        self.history_mag: Deque[float] = deque([1.0] * buffer_size, maxlen=buffer_size)

        self.setMinimumHeight(180)
        self.setStyleSheet("background-color: #0D1117;")

    def add_sample(self, ax: float, ay: float, az: float, mag: float) -> None:
        self.history_x.append(ax)
        self.history_y.append(ay)
        self.history_z.append(az)
        self.history_mag.append(mag)
        self.update()

    def set_threshold(self, threshold: float) -> None:
        self.threshold_g = threshold
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin_left = 40
        margin_right = 20
        margin_top = 20
        margin_bottom = 20
        plot_w = w - margin_left - margin_right
        plot_h = h - margin_top - margin_bottom

        # Background
        painter.fillRect(self.rect(), QColor(13, 17, 23))

        # Y scale: -3.0g to +3.0g (or 0 to 4g)
        min_g = -2.5
        max_g = 3.5

        def g_to_y(g_val: float) -> float:
            normalized = (g_val - min_g) / (max_g - min_g)
            return margin_top + plot_h * (1.0 - normalized)

        # Draw Grid & Y Labels
        painter.setPen(QPen(QColor(33, 38, 45), 1, Qt.DashLine))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        for g_level in [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0]:
            y = g_to_y(g_level)
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))
            painter.setPen(QColor(139, 148, 158))
            painter.drawText(5, int(y + 4), f"{g_level:+.1f}g")
            painter.setPen(QPen(QColor(33, 38, 45), 1, Qt.DashLine))

        # Draw Vibration Threshold Line
        y_thresh = g_to_y(self.threshold_g)
        painter.setPen(QPen(QColor(255, 51, 75, 200), 1.5, Qt.DashDotLine))
        painter.drawLine(margin_left, int(y_thresh), w - margin_right, int(y_thresh))
        painter.drawText(w - 110, int(y_thresh - 4), f"Threshold {self.threshold_g:.2f}g")

        # Plot curves
        dx = plot_w / (self.buffer_size - 1)

        def draw_series(data: Deque[float], color: QColor, width: float = 1.5):
            points = []
            for i, val in enumerate(data):
                px = margin_left + i * dx
                py = g_to_y(val)
                points.append(QPointF(px, py))
            painter.setPen(QPen(color, width))
            painter.drawPolyline(QPolygonF(points))

        draw_series(self.history_x, QColor(0, 210, 255, 180), 1.0)       # Ax: Neon Cyan
        draw_series(self.history_y, QColor(255, 183, 3, 180), 1.0)       # Ay: Amber
        draw_series(self.history_z, QColor(139, 148, 158, 140), 1.0)     # Az: Grey
        draw_series(self.history_mag, QColor(0, 230, 118), 2.0)          # Mag: Bright Green

        # Legend top-right
        painter.fillRect(w - 220, 5, 200, 22, QColor(22, 27, 34, 200))
        painter.setPen(QColor(0, 210, 255))
        painter.drawText(w - 210, 20, "X")
        painter.setPen(QColor(255, 183, 3))
        painter.drawText(w - 180, 20, "Y")
        painter.setPen(QColor(139, 148, 158))
        painter.drawText(w - 150, 20, "Z")
        painter.setPen(QColor(0, 230, 118))
        painter.drawText(w - 120, 20, "Magnitude")
