"""
Tab 1 — Overview Component.
Primary driver cockpit instrument cluster combining live video, gauges, and safety status.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
)
from raspberry_pi.gui.widgets.video_widget import VideoWidget
from raspberry_pi.gui.widgets.gauge_widget import SpeedometerWidget, GForceMeterWidget


class TabOverview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Left Column: Live Annotated Video Feed (Takes 65% width)
        left_panel = QVBoxLayout()
        self.video_widget = VideoWidget(title="Live Front Perception HUD")
        left_panel.addWidget(self.video_widget, stretch=1)
        main_layout.addLayout(left_panel, stretch=65)

        # Right Column: Instrument Cluster & Quick Metrics (35% width)
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)

        # Cockpit Gauges (Speedometer & G-Force)
        gauges_frame = QFrame()
        gauges_frame.setProperty("card", True)
        gauges_layout = QHBoxLayout(gauges_frame)
        self.speedometer = SpeedometerWidget()
        self.g_meter = GForceMeterWidget()
        gauges_layout.addWidget(self.speedometer)
        gauges_layout.addWidget(self.g_meter)
        right_panel.addWidget(gauges_frame)

        # ADAS Lane & Traffic State Card
        adas_card = QFrame()
        adas_card.setProperty("card", True)
        adas_layout = QGridLayout(adas_card)
        adas_layout.setSpacing(8)

        self.lbl_lane_status = QLabel("LANE: NO SIGNAL (BRAIN OFFLINE)")
        self.lbl_lane_status.setStyleSheet("color: #FF334B; font-weight: bold; font-size: 13px;")
        adas_layout.addWidget(self.lbl_lane_status, 0, 0, 1, 2)

        self.lbl_traffic_light = QLabel("TRAFFIC LIGHT: NO SIGNAL")
        self.lbl_traffic_light.setStyleSheet("color: #8B949E; font-weight: bold;")
        adas_layout.addWidget(self.lbl_traffic_light, 1, 0)

        self.lbl_active_sign = QLabel("SPEED LIMIT: --")
        self.lbl_active_sign.setStyleSheet("color: #8B949E; font-weight: bold;")
        adas_layout.addWidget(self.lbl_active_sign, 1, 1)

        self.lbl_objects_summary = QLabel("DETECTED OBJECTS: NO SIGNAL (BRAIN OFFLINE)")
        self.lbl_objects_summary.setStyleSheet("color: #8B949E;")
        adas_layout.addWidget(self.lbl_objects_summary, 2, 0, 1, 2)

        right_panel.addWidget(adas_card)

        # Edge Telemetry Summary Card
        telemetry_card = QFrame()
        telemetry_card.setProperty("card", True)
        tel_layout = QGridLayout(telemetry_card)

        self.lbl_gps_summary = QLabel("GPS: SIGNAL LOST (0 SATS)")
        self.lbl_accel_summary = QLabel("ACCEL: SENSOR DISCONNECTED")
        self.lbl_link_summary = QLabel("BRAIN: NOT CONNECTED")

        self.lbl_gps_summary.setStyleSheet("color: #FF334B;")
        self.lbl_accel_summary.setStyleSheet("color: #FF334B;")
        self.lbl_link_summary.setStyleSheet("color: #FF334B;")

        tel_layout.addWidget(self.lbl_gps_summary, 0, 0)
        tel_layout.addWidget(self.lbl_accel_summary, 1, 0)
        tel_layout.addWidget(self.lbl_link_summary, 2, 0)

        right_panel.addWidget(telemetry_card)
        right_panel.addStretch()

        main_layout.addLayout(right_panel, stretch=35)

    def update_speed(self, speed_kmh: float) -> None:
        self.speedometer.set_speed(speed_kmh)

    def update_g_force(self, g_val: float) -> None:
        self.g_meter.set_g_force(g_val)

    def update_threshold(self, threshold_g: float) -> None:
        self.g_meter.set_threshold(threshold_g)

    def update_lane_status(self, detected: bool, departure: str, offset_m: float) -> None:
        if not detected:
            self.lbl_lane_status.setText("LANE: SEARCHING BOUNDARIES")
            self.lbl_lane_status.setStyleSheet("color: #8B949E; font-weight: bold;")
        elif departure == "NONE":
            self.lbl_lane_status.setText(f"LANE: IN-LANE (OFFSET: {offset_m:+.2f}m)")
            self.lbl_lane_status.setStyleSheet("color: #00E676; font-weight: bold;")
        else:
            self.lbl_lane_status.setText(f"LANE: DEPARTURE {departure}!")
            self.lbl_lane_status.setStyleSheet("color: #FF334B; font-weight: bold;")

    def update_traffic_light(self, detected: bool, state: str, conf: float) -> None:
        if not detected or state == "UNKNOWN":
            self.lbl_traffic_light.setText("TRAFFIC LIGHT: NONE")
            self.lbl_traffic_light.setStyleSheet("color: #8B949E; font-weight: bold;")
        else:
            color_hex = "#00E676" if state == "GREEN" else "#FFB703" if state == "YELLOW" else "#FF334B"
            self.lbl_traffic_light.setText(f"TRAFFIC LIGHT: {state} ({conf*100:.0f}%)")
            self.lbl_traffic_light.setStyleSheet(f"color: {color_hex}; font-weight: bold;")

    def update_objects_summary(self, count: int, closest_dist_m: float) -> None:
        if count == 0:
            self.lbl_objects_summary.setText("DETECTED OBJECTS: NONE")
        else:
            dist_str = f" | Closest: {closest_dist_m:.1f}m" if closest_dist_m > 0 else ""
            self.lbl_objects_summary.setText(f"DETECTED OBJECTS: {count} TRACKED{dist_str}")

    def set_brain_disconnected(self) -> None:
        self.lbl_lane_status.setText("LANE: NO SIGNAL (BRAIN OFFLINE)")
        self.lbl_lane_status.setStyleSheet("color: #FF334B; font-weight: bold; font-size: 13px;")
        self.lbl_traffic_light.setText("TRAFFIC LIGHT: NO SIGNAL")
        self.lbl_traffic_light.setStyleSheet("color: #8B949E; font-weight: bold;")
        self.lbl_active_sign.setText("SPEED LIMIT: --")
        self.lbl_objects_summary.setText("DETECTED OBJECTS: NO SIGNAL (BRAIN OFFLINE)")
        self.lbl_link_summary.setText("BRAIN: NOT CONNECTED")
        self.lbl_link_summary.setStyleSheet("color: #FF334B;")

    def set_sensors_disconnected(self) -> None:
        self.lbl_gps_summary.setText("GPS: SIGNAL LOST (0 SATS)")
        self.lbl_gps_summary.setStyleSheet("color: #FF334B;")
        self.lbl_accel_summary.setText("ACCEL: SENSOR DISCONNECTED")
        self.lbl_accel_summary.setStyleSheet("color: #FF334B;")
        self.speedometer.set_speed(0.0)
        self.g_meter.set_g_force(0.0)
