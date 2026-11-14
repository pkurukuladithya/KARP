"""
Main Application Window for KARP ADAS Raspberry Pi HMI.
Integrates Header status bar, dynamic alert notification bar, and 7 navigation tabs.
"""

from typing import Optional
from PySide6.QtCore import Qt, QSize, Signal, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut, QImage
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QFrame,
    QStatusBar,
)

from raspberry_pi.gui.styles.dark_theme import DARK_THEME_QSS
from raspberry_pi.gui.widgets.status_chip import StatusChip
from raspberry_pi.gui.widgets.alert_banner import AlertBanner
from raspberry_pi.gui.components.tab_overview import TabOverview
from raspberry_pi.gui.components.tab_live_vision import TabLiveVision
from raspberry_pi.gui.components.tab_sensors import TabSensors
from raspberry_pi.gui.components.tab_map import TabMap
from raspberry_pi.gui.components.tab_vibration import TabVibration
from raspberry_pi.gui.components.tab_hardware import TabHardware
from raspberry_pi.gui.components.tab_settings import TabSettings
from shared.config.system_config import get_config
from shared.protocols.message_schemas import SensorTelemetry, AiTelemetry


class MainWindow(QMainWindow):
    # Signals emitted from GUI to Controller/Workers
    threshold_changed = Signal(float, bool)
    actuator_override = Signal(dict)
    config_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()

        self.setWindowTitle("KARP ADAS — Advanced Driver Assistance System")
        self.resize(1280, 720)
        self.setMinimumSize(1024, 600)

        # Apply Automotive Dark Stylesheet
        self.setStyleSheet(DARK_THEME_QSS)

        # Setup Central Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Header Bar with System Status Chips
        self._init_header_bar(main_layout)

        # 2. Dynamic Safety Alert Banner
        self.alert_banner = AlertBanner()
        self.alert_banner.set_alert("HARDWARE DISCONNECTED — BRAIN & ESP32 OFFLINE", "WARNING")
        main_layout.addWidget(self.alert_banner)

        # 3. Main 7 Navigation Tabs
        self._init_tabs(main_layout)

        # 4. Keyboard Shortcuts (Kiosk & Navigation)
        self._init_shortcuts()

        # Check fullscreen preference
        if self.config.get("gui", "fullscreen", False):
            self.showFullScreen()

        self._ai_connected = False
        self._last_ai_frame_time = 0.0

    def _init_header_bar(self, layout: QVBoxLayout) -> None:
        header_frame = QFrame()
        header_frame.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(10)

        # Branding
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_title = QLabel("KARP ADAS")
        lbl_title.setObjectName("HeaderTitle")
        lbl_sub = QLabel("GPU PERCEPTION & VEHICLE TELEMETRY")
        lbl_sub.setObjectName("HeaderSubtitle")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Status Chips
        self.chip_ai = StatusChip("BRAIN", "NOT CONNECTED", StatusChip.STATE_ERROR)
        self.chip_esp32 = StatusChip("ESP32", "DISCONNECTED", StatusChip.STATE_ERROR)
        self.chip_gps = StatusChip("GNSS", "SIGNAL LOST", StatusChip.STATE_ERROR)
        self.chip_cam = StatusChip("CAMERA", "CLOSED", StatusChip.STATE_ERROR)
        self.chip_mode = StatusChip("MODE", "REAL HARDWARE", StatusChip.STATE_OK)

        header_layout.addWidget(self.chip_ai)
        header_layout.addWidget(self.chip_esp32)
        header_layout.addWidget(self.chip_gps)
        header_layout.addWidget(self.chip_cam)
        header_layout.addWidget(self.chip_mode)

        layout.addWidget(header_frame)

    def _init_tabs(self, layout: QVBoxLayout) -> None:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_overview = TabOverview()
        self.tab_live_vision = TabLiveVision()
        self.tab_sensors = TabSensors()
        self.tab_map = TabMap()
        self.tab_vibration = TabVibration(
            initial_threshold=float(self.config.get("sensors", "vibration_threshold_g", 2.20))
        )
        self.tab_hardware = TabHardware()
        self.tab_settings = TabSettings()

        self.tabs.addTab(self.tab_overview, "1. OVERVIEW")
        self.tabs.addTab(self.tab_live_vision, "2. LIVE VISION")
        self.tabs.addTab(self.tab_sensors, "3. SENSORS")
        self.tabs.addTab(self.tab_map, "4. GPS MAP")
        self.tabs.addTab(self.tab_vibration, "5. ROAD CONDITION")
        self.tabs.addTab(self.tab_hardware, "6. HARDWARE")
        self.tabs.addTab(self.tab_settings, "7. SETTINGS")

        # Connect internal child signals
        self.tab_vibration.threshold_updated.connect(self._on_threshold_changed)
        self.tab_live_vision.confidence_changed.connect(self._on_confidence_changed)
        self.tab_hardware.actuator_cmd.connect(self._on_actuator_override)
        self.tab_settings.settings_saved.connect(self._on_settings_saved)

        layout.addWidget(self.tabs, stretch=1)

    def _init_shortcuts(self) -> None:
        # F11 Toggle Fullscreen / Kiosk
        shortcut_f11 = QShortcut(QKeySequence(Qt.Key_F11), self)
        shortcut_f11.activated.connect(self.toggle_fullscreen)

        # Esc to exit fullscreen
        shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        shortcut_esc.activated.connect(self.showNormal)

        # Tab navigation shortcuts Ctrl+1 to Ctrl+7
        for i in range(7):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)
            shortcut.activated.connect(lambda idx=i: self.tabs.setCurrentIndex(idx))

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # Slot updates from background worker threads
    @Slot(QImage, float, float)
    def on_video_frame(self, image: QImage, fps: float, latency_ms: float) -> None:
        """Called when return annotated video stream is received from Laptop AI co-processor."""
        import time
        self._ai_connected = True
        self._last_ai_frame_time = time.time()
        self.tab_overview.video_widget.update_frame(image, fps, latency_ms)
        self.tab_live_vision.video_widget.update_frame(image, fps, latency_ms)
        self.chip_cam.set_status(f"{fps:.0f} FPS", StatusChip.STATE_OK if fps >= 15 else StatusChip.STATE_WARN)

    @Slot(bool, str)
    def on_camera_status_changed(self, is_open: bool, msg: str) -> None:
        if is_open:
            self.chip_cam.set_status("ONLINE", StatusChip.STATE_OK)
        else:
            self.chip_cam.set_status("CLOSED", StatusChip.STATE_ERROR)
            if not self._ai_connected:
                self.tab_overview.video_widget.set_offline_status("CAMERA CLOSED / NO VIDEO SIGNAL")
                self.tab_live_vision.video_widget.set_offline_status("CAMERA CLOSED / NO VIDEO SIGNAL")

    @Slot(object, int, int)
    def on_local_camera_frame(self, frame_bgr, frame_id: int, timestamp_ms: int) -> None:
        """Called by local camera worker. If Laptop AI is offline, display raw camera feed with clear notice!"""
        import time
        if not self._ai_connected or (time.time() - self._last_ai_frame_time > 1.5):
            import cv2
            h, w, ch = frame_bgr.shape
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
            self.tab_overview.video_widget.update_frame(qimg, fps=30.0, latency_ms=0.0)
            self.tab_live_vision.video_widget.update_frame(qimg, fps=30.0, latency_ms=0.0)
            self.chip_cam.set_status("30 FPS (RAW)", StatusChip.STATE_OK)

    @Slot(object)
    def on_ai_telemetry(self, telemetry: AiTelemetry) -> None:
        # Update link chip
        self.chip_ai.set_status(f"ONLINE ({telemetry.performance.inference_fps:.0f} FPS)", StatusChip.STATE_OK)

        # Update diagnostics
        self.tab_live_vision.update_diagnostics(
            telemetry.performance.device,
            telemetry.performance.inference_fps,
            telemetry.performance.pipeline_latency_ms,
            telemetry.performance.dropped_frames,
        )
        self.tab_live_vision.update_objects_table(telemetry.objects)

        # Update lane and road cues
        self.tab_overview.update_lane_status(
            telemetry.lanes.detected,
            telemetry.lanes.departure_warning,
            telemetry.lanes.vehicle_offset_m,
        )
        self.tab_overview.update_traffic_light(
            telemetry.traffic_light.detected,
            telemetry.traffic_light.state,
            telemetry.traffic_light.confidence,
        )

        closest_dist = min([o.estimated_distance_m for o in telemetry.objects if o.estimated_distance_m is not None], default=0.0)
        self.tab_overview.update_objects_summary(len(telemetry.objects), closest_dist)

        # Update dynamic warning banner
        if telemetry.warnings:
            highest_warn = telemetry.warnings[0]
            self.alert_banner.set_alert(highest_warn.message, highest_warn.level)
        elif telemetry.lanes.departure_warning != "NONE":
            self.alert_banner.set_alert(f"LANE DEPARTURE WARNING — DRIFTING {telemetry.lanes.departure_warning}!", "CRITICAL")
        else:
            self.alert_banner.set_alert("ALL SYSTEMS OPERATIONAL — ADAS PERCEPTION ACTIVE", "NORMAL")

    @Slot(object)
    def on_sensor_telemetry(self, telemetry: SensorTelemetry) -> None:
        # Accel
        ax = telemetry.accel.ax_g
        ay = telemetry.accel.ay_g
        az = telemetry.accel.az_g
        mag = telemetry.accel.magnitude_g
        vibe_detected = telemetry.accel.vibration_detected

        self.tab_overview.update_g_force(mag)
        self.tab_sensors.update_accel_data(ax, ay, az, mag, 20.0, vibe_detected)
        self.tab_vibration.update_vibration(ax, ay, az, mag, vibe_detected)

        # GPS
        lat = telemetry.gps.latitude
        lon = telemetry.gps.longitude
        alt = telemetry.gps.altitude_m
        spd = telemetry.gps.speed_kmh
        hdg = telemetry.gps.heading_deg
        sats = telemetry.gps.satellites
        fix = telemetry.gps.fix_quality
        is_sim = telemetry.gps.is_simulated

        self.tab_overview.update_speed(spd)
        self.tab_sensors.update_gps_data(lat, lon, alt, spd, sats, fix, is_sim)
        self.tab_map.update_gps(lat, lon, alt, spd, hdg, sats, fix, is_sim)

        # Status Chips
        if is_sim:
            self.chip_mode.set_status("SIMULATION", StatusChip.STATE_SIM)
            self.chip_gps.set_status(f"SIM ({spd:.0f} km/h)", StatusChip.STATE_SIM)
            self.chip_esp32.set_status("SIMULATED", StatusChip.STATE_SIM)
        else:
            self.chip_mode.set_status("HARDWARE", StatusChip.STATE_OK)
            self.chip_esp32.set_status("CONNECTED", StatusChip.STATE_OK)
            if fix > 0:
                self.chip_gps.set_status(f"{sats} SATS (FIX)", StatusChip.STATE_OK)
            else:
                self.chip_gps.set_status("SIGNAL LOST", StatusChip.STATE_ERROR)

    @Slot(bool)
    def on_ai_connection_changed(self, connected: bool) -> None:
        self._ai_connected = connected
        if connected:
            self.chip_ai.set_status("CONNECTED", StatusChip.STATE_OK)
            self.alert_banner.set_alert("BRAIN CONNECTED — AI PERCEPTION ACTIVE", "NORMAL")
        else:
            self.chip_ai.set_status("NOT CONNECTED", StatusChip.STATE_ERROR)
            self.alert_banner.set_alert("BRAIN NOT CONNECTED — WAITING FOR LAPTOP AI", "WARNING")
            self.tab_overview.set_brain_disconnected()
            self.tab_live_vision.set_disconnected()

    @Slot(bool)
    def on_esp32_connection_changed(self, connected: bool) -> None:
        if connected:
            self.chip_esp32.set_status("CONNECTED", StatusChip.STATE_OK)
            self.tab_hardware.update_hardware_status(True, True, True)
        else:
            self.chip_esp32.set_status("DISCONNECTED", StatusChip.STATE_ERROR)
            self.chip_gps.set_status("SIGNAL LOST", StatusChip.STATE_ERROR)
            self.tab_overview.set_sensors_disconnected()
            self.tab_sensors.set_disconnected()
            self.tab_vibration.set_disconnected()
            self.tab_hardware.update_hardware_status(False, False, False)

    def _on_threshold_changed(self, threshold_g: float, persist_to_disk: bool) -> None:
        self.tab_overview.update_threshold(threshold_g)
        self.threshold_changed.emit(threshold_g, persist_to_disk)

    def _on_confidence_changed(self, conf: float) -> None:
        self.config_updated.emit({"confidence_threshold": conf})

    def _on_actuator_override(self, cmd: dict) -> None:
        self.actuator_override.emit(cmd)

    def _on_settings_saved(self, settings: dict) -> None:
        self.config_updated.emit(settings)
        self.alert_banner.set_alert("CONFIGURATION SAVED & PERSISTED SUCCESSFULLY", "INFO")
