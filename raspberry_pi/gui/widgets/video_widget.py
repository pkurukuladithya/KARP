"""
High-Performance Video Display Widget for PySide6.
Handles frame rendering with aspect-ratio letterboxing, HUD overlay, and offline fallback.
"""

from typing import Optional
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class VideoWidget(QWidget):
    def __init__(self, title: str = "Front Road Camera", parent=None):
        super().__init__(parent)
        self._title = title
        self._current_image: Optional[QImage] = None
        self._fps: float = 0.0
        self._latency_ms: float = 0.0
        self._resolution_str: str = "--"
        self._status_text: str = "CAMERA DISCONNECTED / NO VIDEO SIGNAL"
        self._show_hud: bool = True

        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #07090E;")

    def set_show_hud(self, show: bool) -> None:
        self._show_hud = show
        self.update()

    def update_frame(self, image: QImage, fps: float = 0.0, latency_ms: float = 0.0) -> None:
        self._current_image = image
        self._fps = fps
        self._latency_ms = latency_ms
        if image and not image.isNull():
            self._resolution_str = f"{image.width()}x{image.height()}"
        self.update()

    def set_offline_status(self, text: str) -> None:
        self._current_image = None
        self._status_text = text
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # No SmoothPixmapTransform: bilinear scaling of every video frame in software
        # is one of the most expensive operations on the Pi 4's CPU.
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Clear background
        painter.fillRect(self.rect(), QColor(7, 9, 14))

        if self._current_image is not None and not self._current_image.isNull():
            # Calculate aspect ratio letterbox
            img_w = self._current_image.width()
            img_h = self._current_image.height()
            widget_w = self.width()
            widget_h = self.height()

            scale = min(widget_w / img_w, widget_h / img_h)
            draw_w = int(img_w * scale)
            draw_h = int(img_h * scale)
            offset_x = (widget_w - draw_w) // 2
            offset_y = (widget_h - draw_h) // 2

            target_rect = QRect(offset_x, offset_y, draw_w, draw_h)
            painter.drawImage(target_rect, self._current_image)
        else:
            self._draw_offline_placeholder(painter)

        if self._show_hud:
            self._draw_hud(painter)

    def _draw_offline_placeholder(self, painter: QPainter) -> None:
        w, h = self.width(), self.height()

        # Draw grid
        painter.setPen(QPen(QColor(30, 38, 50), 1, Qt.DashLine))
        for x in range(0, w, 50):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 50):
            painter.drawLine(0, y, w, y)

        # Draw crosshair in center
        cx, cy = w // 2, h // 2
        painter.setPen(QPen(QColor(0, 210, 255, 120), 2))
        painter.drawEllipse(QPoint(cx, cy), 40, 40)
        painter.drawLine(cx - 50, cy, cx + 50, cy)
        painter.drawLine(cx, cy - 50, cx, cy + 50)

        # Status text
        painter.setPen(QPen(QColor(255, 183, 3)))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(0, 70, 0, 0),
            Qt.AlignHCenter | Qt.AlignVCenter,
            self._status_text,
        )

    def _draw_hud(self, painter: QPainter) -> None:
        # Title banner top-left
        painter.fillRect(QRect(10, 10, 240, 32), QColor(16, 22, 30, 190))
        painter.setPen(QPen(QColor(0, 210, 255)))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(20, 31, self._title)

        # FPS & Latency stats top-right
        stats_text = f"FPS: {self._fps:4.1f} | Latency: {self._latency_ms:4.1f}ms | {self._resolution_str}"
        painter.fillRect(QRect(self.width() - 290, 10, 280, 32), QColor(16, 22, 30, 190))
        painter.setPen(QPen(QColor(0, 230, 118) if self._fps >= 20 else QColor(255, 183, 3)))
        painter.drawText(self.width() - 280, 31, stats_text)
