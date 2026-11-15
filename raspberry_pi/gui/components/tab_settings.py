"""
Tab 7 — System Settings Component.
Comprehensive configuration editor with parameter persistence and simulation mode toggle.
"""

from typing import Any, Dict
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QCheckBox,
    QPushButton,
    QScrollArea,
)
from raspberry_pi.gui.styles.style_utils import set_style
from shared.config.system_config import get_config


class TabSettings(QWidget):
    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        set_style(scroll, "QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # 1. Network Settings Card
        net_card = QFrame()
        net_card.setProperty("card", True)
        net_layout = QGridLayout(net_card)
        net_title = QLabel("DISTRIBUTED NETWORK CONFIGURATION")
        set_style(net_title, "color: #00D2FF; font-weight: bold; font-size: 14px;")
        net_layout.addWidget(net_title, 0, 0, 1, 4)

        net_layout.addWidget(QLabel("Laptop AI IP Address:"), 1, 0)
        self.edit_laptop_ip = QLineEdit(str(self.config.get("network", "laptop_ip", "192.168.1.100")))
        net_layout.addWidget(self.edit_laptop_ip, 1, 1)

        net_layout.addWidget(QLabel("Metadata WebSocket Port:"), 1, 2)
        self.spin_ws_port = QSpinBox()
        self.spin_ws_port.setRange(1024, 65535)
        self.spin_ws_port.setValue(int(self.config.get("network", "metadata_ws_port", 8765)))
        net_layout.addWidget(self.spin_ws_port, 1, 3)

        net_layout.addWidget(QLabel("Pi -> Laptop Video Port:"), 2, 0)
        self.spin_port_tx = QSpinBox()
        self.spin_port_tx.setRange(1024, 65535)
        self.spin_port_tx.setValue(int(self.config.get("network", "video_port_pi_to_laptop", 5000)))
        net_layout.addWidget(self.spin_port_tx, 2, 1)

        net_layout.addWidget(QLabel("Laptop -> Pi Video Port:"), 2, 2)
        self.spin_port_rx = QSpinBox()
        self.spin_port_rx.setRange(1024, 65535)
        self.spin_port_rx.setValue(int(self.config.get("network", "video_port_laptop_to_pi", 5001)))
        net_layout.addWidget(self.spin_port_rx, 2, 3)

        layout.addWidget(net_card)

        # 2. Camera & Video Acquisition Card
        cam_card = QFrame()
        cam_card.setProperty("card", True)
        cam_layout = QGridLayout(cam_card)
        cam_title = QLabel("CAMERA ACQUISITION & ENCODING")
        set_style(cam_title, "color: #00D2FF; font-weight: bold; font-size: 14px;")
        cam_layout.addWidget(cam_title, 0, 0, 1, 4)

        cam_layout.addWidget(QLabel("Camera Device Index:"), 1, 0)
        self.spin_cam_idx = QSpinBox()
        self.spin_cam_idx.setRange(0, 10)
        self.spin_cam_idx.setValue(int(self.config.get("video", "camera_index", 0)))
        cam_layout.addWidget(self.spin_cam_idx, 1, 1)

        cam_layout.addWidget(QLabel("Video Resolution:"), 1, 2)
        self.combo_res = QComboBox()
        self.combo_res.addItems(["1280x720 (720p HD)", "640x480 (VGA)", "1920x1080 (1080p FHD)"])
        cam_layout.addWidget(self.combo_res, 1, 3)

        cam_layout.addWidget(QLabel("Target Frame Rate:"), 2, 0)
        self.combo_fps = QComboBox()
        self.combo_fps.addItems(["30 FPS (Recommended)", "20 FPS", "15 FPS"])
        cam_layout.addWidget(self.combo_fps, 2, 1)

        cam_layout.addWidget(QLabel("Stream Bitrate (bps):"), 2, 2)
        self.spin_bitrate = QSpinBox()
        self.spin_bitrate.setRange(500000, 10000000)
        self.spin_bitrate.setSingleStep(250000)
        self.spin_bitrate.setValue(int(self.config.get("video", "bitrate", 2500000)))
        cam_layout.addWidget(self.spin_bitrate, 2, 3)

        layout.addWidget(cam_card)

        # 3. Microcontroller & Sensor Card
        sens_card = QFrame()
        sens_card.setProperty("card", True)
        sens_layout = QGridLayout(sens_card)
        sens_title = QLabel("ESP32 HARDWARE & CALIBRATION")
        set_style(sens_title, "color: #00D2FF; font-weight: bold; font-size: 14px;")
        sens_layout.addWidget(sens_title, 0, 0, 1, 4)

        sens_layout.addWidget(QLabel("ESP32 Serial Port:"), 1, 0)
        self.edit_esp_port = QLineEdit(str(self.config.get("sensors", "esp32_port", "/dev/ttyUSB0")))
        sens_layout.addWidget(self.edit_esp_port, 1, 1)

        sens_layout.addWidget(QLabel("Serial Baud Rate:"), 1, 2)
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["115200", "9600", "57600", "230400"])
        sens_layout.addWidget(self.combo_baud, 1, 3)

        sens_layout.addWidget(QLabel("Vibration Alert Threshold:"), 2, 0)
        self.spin_thresh = QDoubleSpinBox()
        self.spin_thresh.setRange(1.0, 5.0)
        self.spin_thresh.setValue(float(self.config.get("sensors", "vibration_threshold_g", 2.20)))
        sens_layout.addWidget(self.spin_thresh, 2, 1)

        sens_layout.addWidget(QLabel("Sensor Update Frequency:"), 2, 2)
        self.spin_update_hz = QSpinBox()
        self.spin_update_hz.setRange(5, 50)
        self.spin_update_hz.setValue(int(self.config.get("sensors", "update_hz", 20)))
        sens_layout.addWidget(self.spin_update_hz, 2, 3)

        layout.addWidget(sens_card)

        # 4. Simulation Mode & Operational Mode Card
        mode_card = QFrame()
        mode_card.setProperty("card", True)
        mode_layout = QHBoxLayout(mode_card)

        self.chk_simulation = QCheckBox("ENABLE SIMULATION MODE (No physical camera or ESP32 required)")
        set_style(self.chk_simulation, "color: #00D2FF; font-weight: bold;")
        self.chk_simulation.setChecked(bool(self.config.get("sensors", "simulation_mode", False)))
        mode_layout.addWidget(self.chk_simulation)

        mode_layout.addStretch()

        self.btn_save_all = QPushButton("Save & Persist All Configurations")
        self.btn_save_all.setObjectName("PrimaryButton")
        self.btn_save_all.clicked.connect(self._on_save_all)
        mode_layout.addWidget(self.btn_save_all)

        layout.addWidget(mode_card)
        layout.addStretch()

        scroll.setWidget(container)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

    def _on_save_all(self) -> None:
        new_settings = {
            "network": {
                "laptop_ip": self.edit_laptop_ip.text().strip(),
                "metadata_ws_port": self.spin_ws_port.value(),
                "video_port_pi_to_laptop": self.spin_port_tx.value(),
                "video_port_laptop_to_pi": self.spin_port_rx.value(),
            },
            "video": {
                "camera_index": self.spin_cam_idx.value(),
                "bitrate": self.spin_bitrate.value(),
            },
            "sensors": {
                "esp32_port": self.edit_esp_port.text().strip(),
                "baud_rate": int(self.combo_baud.currentText()),
                "vibration_threshold_g": self.spin_thresh.value(),
                "update_hz": self.spin_update_hz.value(),
                "simulation_mode": self.chk_simulation.isChecked(),
            },
        }

        # Update in-memory and write atomic to disk
        for section, values in new_settings.items():
            self.config.update_section(section, values, save_to_disk=False)
        self.config.save()
        self.settings_saved.emit(new_settings)
