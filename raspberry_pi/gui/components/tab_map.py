"""
Tab 4 — GPS Location Component.
Large offline vector navigation map with real-time waypoint tracking.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from raspberry_pi.gui.widgets.map_widget import MapWidget


class TabMap(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header Info Card
        header_card = QFrame()
        header_card.setProperty("card", True)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(12, 8, 12, 8)

        lbl_title = QLabel("AUTONOMOUS VEHICLE VECTOR NAVIGATION")
        lbl_title.setStyleSheet("color: #00D2FF; font-weight: bold; font-size: 14px;")
        header_layout.addWidget(lbl_title)

        header_layout.addStretch()

        self.lbl_mode_badge = QLabel("DATA SOURCE: REAL GNSS HARDWARE")
        self.lbl_mode_badge.setStyleSheet("color: #00E676; font-weight: bold;")
        header_layout.addWidget(self.lbl_mode_badge)

        layout.addWidget(header_card)

        # Vector Map Canvas
        self.map_widget = MapWidget()
        layout.addWidget(self.map_widget, stretch=1)

    def update_gps(
        self,
        lat: float,
        lon: float,
        alt: float,
        speed: float,
        heading: float,
        sats: int,
        fix: int,
        is_sim: bool,
    ) -> None:
        self.map_widget.update_gps(lat, lon, alt, speed, heading, sats, fix, is_sim)
        if is_sim:
            self.lbl_mode_badge.setText("DATA SOURCE: SYNTHETIC SIMULATION (MOCK TRAJECTORY)")
            self.lbl_mode_badge.setStyleSheet("color: #00D2FF; font-weight: bold;")
        elif fix > 0:
            self.lbl_mode_badge.setText(f"DATA SOURCE: LIVE GNSS SATELLITES ({sats} TRACKED)")
            self.lbl_mode_badge.setStyleSheet("color: #00E676; font-weight: bold;")
        else:
            self.lbl_mode_badge.setText("DATA SOURCE: SEARCHING FOR SATELLITE FIX...")
            self.lbl_mode_badge.setStyleSheet("color: #FF334B; font-weight: bold;")
