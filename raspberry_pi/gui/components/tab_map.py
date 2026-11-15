"""
Tab 4 — GPS Location Component with OpenStreetMap.
Renders live OpenStreetMap navigation tiles, vehicle marker, and true hardware satellite fix status.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
)
from raspberry_pi.gui.styles.style_utils import set_style
from raspberry_pi.gui.widgets.osm_map_widget import OpenStreetMapWidget


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

        lbl_title = QLabel("OPENSTREETMAP VEHICLE NAVIGATION")
        set_style(lbl_title, "color: #00D2FF; font-weight: bold; font-size: 14px;")
        header_layout.addWidget(lbl_title)

        header_layout.addStretch()

        self.lbl_mode_badge = QLabel("GPS STATUS: SIGNAL LOST (NO SATELLITE FIX)")
        set_style(self.lbl_mode_badge, "color: #FF334B; font-weight: bold;")
        header_layout.addWidget(self.lbl_mode_badge)

        layout.addWidget(header_card)

        # OpenStreetMap Viewport
        self.map_widget = OpenStreetMapWidget()
        layout.addWidget(self.map_widget, stretch=1)

        # Bottom Coordinates & Signal Bar
        coord_card = QFrame()
        coord_card.setProperty("card", True)
        coord_layout = QGridLayout(coord_card)
        coord_layout.setContentsMargins(12, 8, 12, 8)

        self.lbl_lat = QLabel("Latitude: --")
        self.lbl_lon = QLabel("Longitude: --")
        self.lbl_alt = QLabel("Altitude: --")
        self.lbl_spd = QLabel("Ground Speed: 0.0 km/h")
        self.lbl_sats = QLabel("Satellites: 0")
        self.lbl_provider = QLabel("Map Engine: OpenStreetMap | Datum: WGS-84")
        set_style(self.lbl_provider, "color: #8B949E; font-size: 11px;")

        coord_layout.addWidget(self.lbl_lat, 0, 0)
        coord_layout.addWidget(self.lbl_lon, 0, 1)
        coord_layout.addWidget(self.lbl_alt, 0, 2)
        coord_layout.addWidget(self.lbl_spd, 1, 0)
        coord_layout.addWidget(self.lbl_sats, 1, 1)
        coord_layout.addWidget(self.lbl_provider, 1, 2)

        layout.addWidget(coord_card)

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
            self.lbl_mode_badge.setText("DATA SOURCE: SIMULATION MODE")
            set_style(self.lbl_mode_badge, "color: #00D2FF; font-weight: bold;")
            self.lbl_lat.setText(f"Latitude: {lat:.6f}°")
            self.lbl_lon.setText(f"Longitude: {lon:.6f}°")
            self.lbl_alt.setText(f"Altitude: {alt:.1f} m")
            self.lbl_spd.setText(f"Ground Speed: {speed:.1f} km/h")
            self.lbl_sats.setText(f"Satellites: {sats}")
        elif fix > 0:
            self.lbl_mode_badge.setText(f"GPS STATUS: 3D SATELLITE FIX ({sats} SATS)")
            set_style(self.lbl_mode_badge, "color: #00E676; font-weight: bold;")
            self.lbl_lat.setText(f"Latitude: {lat:.6f}°")
            self.lbl_lon.setText(f"Longitude: {lon:.6f}°")
            self.lbl_alt.setText(f"Altitude: {alt:.1f} m")
            self.lbl_spd.setText(f"Ground Speed: {speed:.1f} km/h")
            self.lbl_sats.setText(f"Satellites: {sats}")
        else:
            self.lbl_mode_badge.setText("GPS STATUS: SIGNAL LOST / WAITING FOR SATELLITE FIX")
            set_style(self.lbl_mode_badge, "color: #FF334B; font-weight: bold;")
            self.lbl_lat.setText("Latitude: --")
            self.lbl_lon.setText("Longitude: --")
            self.lbl_alt.setText("Altitude: --")
            self.lbl_spd.setText("Ground Speed: 0.0 km/h")
            self.lbl_sats.setText(f"Satellites: {sats}")
