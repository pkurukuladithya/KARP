"""
Tab 3 — Vehicle Sensors Component.
Comprehensive telemetry dashboard displaying GPS and triaxial accelerometer streams.
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
from raspberry_pi.gui.styles.style_utils import set_style
from raspberry_pi.gui.widgets.sensor_charts import AccelerometerChartWidget


class TabSensors(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Top Row: Numeric Sensor Stat Cards
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # 1. Accelerometer Card
        accel_card = QFrame()
        accel_card.setProperty("card", True)
        accel_layout = QGridLayout(accel_card)

        title_accel = QLabel("TRIAXIAL ACCELEROMETER (I2C)")
        set_style(title_accel, "color: #00D2FF; font-weight: bold; font-size: 14px;")
        accel_layout.addWidget(title_accel, 0, 0, 1, 2)

        self.lbl_ax = QLabel("X-Axis: -- g")
        self.lbl_ay = QLabel("Y-Axis: -- g")
        self.lbl_az = QLabel("Z-Axis: -- g")
        self.lbl_mag = QLabel("Magnitude: -- g")
        self.lbl_accel_hz = QLabel("Sampling Rate: 0 Hz (OFFLINE)")
        self.lbl_vibe_event = QLabel("Vibration Event: SENSOR DISCONNECTED")
        set_style(self.lbl_vibe_event, "color: #FF334B; font-weight: bold;")

        accel_layout.addWidget(self.lbl_ax, 1, 0)
        accel_layout.addWidget(self.lbl_ay, 1, 1)
        accel_layout.addWidget(self.lbl_az, 2, 0)
        accel_layout.addWidget(self.lbl_mag, 2, 1)
        accel_layout.addWidget(self.lbl_accel_hz, 3, 0)
        accel_layout.addWidget(self.lbl_vibe_event, 3, 1)

        top_row.addWidget(accel_card, stretch=50)

        # 2. GPS Card
        gps_card = QFrame()
        gps_card.setProperty("card", True)
        gps_layout = QGridLayout(gps_card)

        title_gps = QLabel("GNSS / GPS SATELLITE RECEIVER (UART)")
        set_style(title_gps, "color: #00D2FF; font-weight: bold; font-size: 14px;")
        gps_layout.addWidget(title_gps, 0, 0, 1, 2)

        self.lbl_lat = QLabel("Latitude: --")
        self.lbl_lon = QLabel("Longitude: --")
        self.lbl_alt = QLabel("Altitude: --")
        self.lbl_speed = QLabel("Ground Speed: 0.0 km/h")
        self.lbl_sats = QLabel("Satellites: 0")
        self.lbl_fix = QLabel("Fix Status: GPS SIGNAL LOST")
        set_style(self.lbl_fix, "color: #FF334B; font-weight: bold;")
        set_style(self.lbl_fix, "color: #FF334B; font-weight: bold;")

        gps_layout.addWidget(self.lbl_lat, 1, 0)
        gps_layout.addWidget(self.lbl_lon, 1, 1)
        gps_layout.addWidget(self.lbl_alt, 2, 0)
        gps_layout.addWidget(self.lbl_speed, 2, 1)
        gps_layout.addWidget(self.lbl_sats, 3, 0)
        gps_layout.addWidget(self.lbl_fix, 3, 1)

        top_row.addWidget(gps_card, stretch=50)
        main_layout.addLayout(top_row)

        # Bottom Row: Real-time Accelerometer Oscilloscope Chart
        chart_card = QFrame()
        chart_card.setProperty("card", True)
        chart_layout = QVBoxLayout(chart_card)

        chart_title = QLabel("REAL-TIME ACCELERATION OSCILLOSCOPE")
        set_style(chart_title, "color: #F0F6FC; font-weight: bold;")
        chart_layout.addWidget(chart_title)

        self.chart = AccelerometerChartWidget()
        chart_layout.addWidget(self.chart, stretch=1)

        main_layout.addWidget(chart_card, stretch=1)

    def update_accel_data(self, ax: float, ay: float, az: float, mag: float, hz: float, vibe_active: bool) -> None:
        self.lbl_ax.setText(f"X-Axis: {ax:+.2f} g")
        self.lbl_ay.setText(f"Y-Axis: {ay:+.2f} g")
        self.lbl_az.setText(f"Z-Axis: {az:+.2f} g")
        self.lbl_mag.setText(f"Magnitude: {mag:.2f} g")
        self.lbl_accel_hz.setText(f"Sampling Rate: {hz:.1f} Hz")

        if vibe_active:
            self.lbl_vibe_event.setText("Vibration Event: DETECTED (POTHOLE/ROUGH)")
            set_style(self.lbl_vibe_event, "color: #FF334B; font-weight: bold;")
        else:
            self.lbl_vibe_event.setText("Vibration Event: NORMAL SURFACE")
            set_style(self.lbl_vibe_event, "color: #00E676; font-weight: bold;")

        self.chart.add_sample(ax, ay, az, mag)

    def update_gps_data(self, lat: float, lon: float, alt: float, speed: float, sats: int, fix: int, is_sim: bool) -> None:
        self.lbl_lat.setText(f"Latitude: {lat:.6f}°")
        self.lbl_lon.setText(f"Longitude: {lon:.6f}°")
        self.lbl_alt.setText(f"Altitude: {alt:.1f} m")
        self.lbl_speed.setText(f"Ground Speed: {speed:.1f} km/h")
        self.lbl_sats.setText(f"Satellites: {sats}")

        if is_sim:
            self.lbl_fix.setText("Fix Status: SIMULATION MODE")
            set_style(self.lbl_fix, "color: #00D2FF; font-weight: bold;")
        elif fix > 0:
            self.lbl_fix.setText(f"Fix Status: 3D FIX (QUAL: {fix})")
            set_style(self.lbl_fix, "color: #00E676; font-weight: bold;")
        else:
            self.lbl_fix.setText("Fix Status: GPS SIGNAL LOST")
            set_style(self.lbl_fix, "color: #FF334B; font-weight: bold;")

    def set_disconnected(self) -> None:
        self.lbl_ax.setText("X-Axis: -- g")
        self.lbl_ay.setText("Y-Axis: -- g")
        self.lbl_az.setText("Z-Axis: -- g")
        self.lbl_mag.setText("Magnitude: -- g")
        self.lbl_accel_hz.setText("Sampling Rate: 0 Hz (OFFLINE)")
        self.lbl_vibe_event.setText("Vibration Event: SENSOR DISCONNECTED")
        set_style(self.lbl_vibe_event, "color: #FF334B; font-weight: bold;")
        self.lbl_lat.setText("Latitude: --")
        self.lbl_lon.setText("Longitude: --")
        self.lbl_alt.setText("Altitude: --")
        self.lbl_speed.setText("Ground Speed: 0.0 km/h")
        self.lbl_sats.setText("Satellites: 0")
        self.lbl_fix.setText("Fix Status: GPS SIGNAL LOST")
        set_style(self.lbl_fix, "color: #FF334B; font-weight: bold;")
