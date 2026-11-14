"""
Tab 5 — Accelerometer & Road Condition Component.
Interactive vibration threshold calibration, dynamic filter sync, and road roughness detection.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QSlider,
    QDoubleSpinBox,
    QPushButton,
)
from raspberry_pi.gui.widgets.sensor_charts import AccelerometerChartWidget


class TabVibration(QWidget):
    threshold_updated = Signal(float, bool)  # (threshold_g, persist_to_disk)

    def __init__(self, initial_threshold: float = 2.20, parent=None):
        super().__init__(parent)
        self._current_threshold = initial_threshold

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Top Section: Control & Threshold Adjustment Card
        ctrl_card = QFrame()
        ctrl_card.setProperty("card", True)
        ctrl_layout = QGridLayout(ctrl_card)
        ctrl_layout.setSpacing(12)

        title = QLabel("ROAD ROUGHNESS & VIBRATION THRESHOLD TUNING")
        title.setStyleSheet("color: #00D2FF; font-weight: bold; font-size: 14px;")
        ctrl_layout.addWidget(title, 0, 0, 1, 4)

        # Threshold Slider & SpinBox
        lbl_adjust = QLabel("Active Threshold (g):")
        lbl_adjust.setStyleSheet("font-weight: bold;")
        ctrl_layout.addWidget(lbl_adjust, 1, 0)

        self.slider_thresh = QSlider(Qt.Horizontal)
        self.slider_thresh.setRange(100, 500)  # 1.00g to 5.00g (step 0.01)
        self.slider_thresh.setValue(int(initial_threshold * 100))
        self.slider_thresh.valueChanged.connect(self._on_slider_changed)
        ctrl_layout.addWidget(self.slider_thresh, 1, 1)

        self.spin_thresh = QDoubleSpinBox()
        self.spin_thresh.setRange(1.0, 5.0)
        self.spin_thresh.setSingleStep(0.05)
        self.spin_thresh.setValue(initial_threshold)
        self.spin_thresh.valueChanged.connect(self._on_spin_changed)
        ctrl_layout.addWidget(self.spin_thresh, 1, 2)

        # Save & Persist Button
        self.btn_save_thresh = QPushButton("Save & Sync to ESP32")
        self.btn_save_thresh.setObjectName("PrimaryButton")
        self.btn_save_thresh.clicked.connect(self._on_save_clicked)
        ctrl_layout.addWidget(self.btn_save_thresh, 1, 3)

        # Status Indicators
        self.lbl_vibe_status = QLabel("ROAD SURFACE: ACCELEROMETER DISCONNECTED")
        self.lbl_vibe_status.setStyleSheet("color: #FF334B; font-weight: bold; font-size: 13px;")
        ctrl_layout.addWidget(self.lbl_vibe_status, 2, 0, 1, 2)

        self.lbl_calib_status = QLabel("CALIBRATION: SENSOR OFFLINE (WAITING FOR ESP32)")
        self.lbl_calib_status.setStyleSheet("color: #8B949E; font-size: 11px;")
        ctrl_layout.addWidget(self.lbl_calib_status, 2, 2, 1, 2)

        main_layout.addWidget(ctrl_card)

        # Middle Section: Waveform Oscilloscope
        chart_card = QFrame()
        chart_card.setProperty("card", True)
        chart_layout = QVBoxLayout(chart_card)
        chart_title = QLabel("DYNAMIC ACCELERATION WAVEFORM & THRESHOLD LINE")
        chart_title.setStyleSheet("color: #F0F6FC; font-weight: bold;")
        chart_layout.addWidget(chart_title)

        self.chart = AccelerometerChartWidget(threshold_g=initial_threshold)
        chart_layout.addWidget(self.chart, stretch=1)
        main_layout.addWidget(chart_card, stretch=1)

        # Bottom Section: Engineering Note / Methodology
        note_card = QFrame()
        note_card.setProperty("card", True)
        note_layout = QVBoxLayout(note_card)
        note_text = QLabel(
            "ENGINEERING NOTE: Raw acceleration includes 1.0g static Earth gravity plus vehicle chassis dynamics. "
            "KARP applies a high-pass digital filter (cutoff 5 Hz) and rolling RMS window to isolate high-frequency road impact vibrations "
            "(potholes, rumble strips) from gentle vehicle maneuvers."
        )
        note_text.setStyleSheet("color: #8B949E; font-size: 11px;")
        note_text.setWordWrap(True)
        note_layout.addWidget(note_text)
        main_layout.addWidget(note_card)

    def _on_slider_changed(self, value: int) -> None:
        val_g = value / 100.0
        self.spin_thresh.blockSignals(True)
        self.spin_thresh.setValue(val_g)
        self.spin_thresh.blockSignals(False)
        self._current_threshold = val_g
        self.chart.set_threshold(val_g)
        self.threshold_updated.emit(val_g, False)

    def _on_spin_changed(self, value: float) -> None:
        self.slider_thresh.blockSignals(True)
        self.slider_thresh.setValue(int(value * 100))
        self.slider_thresh.blockSignals(False)
        self._current_threshold = value
        self.chart.set_threshold(value)
        self.threshold_updated.emit(value, False)

    def _on_save_clicked(self) -> None:
        self.threshold_updated.emit(self._current_threshold, True)
        self.lbl_calib_status.setText(f"PERSISTED THRESHOLD: {self._current_threshold:.2f}g SYNCED TO DISK & ESP32")
        self.lbl_calib_status.setStyleSheet("color: #00D2FF; font-size: 11px; font-weight: bold;")

    def update_vibration(self, ax: float, ay: float, az: float, mag: float, vibe_detected: bool) -> None:
        self.chart.add_sample(ax, ay, az, mag)
        if vibe_detected:
            self.lbl_vibe_status.setText(f"ROAD SURFACE: SEVERE VIBRATION DETECTED ({mag:.2f}g > {self._current_threshold:.2f}g)!")
            self.lbl_vibe_status.setStyleSheet("color: #FF334B; font-weight: bold; font-size: 13px;")
        else:
            self.lbl_vibe_status.setText(f"ROAD SURFACE: NORMAL PAVEMENT ({mag:.2f}g)")
            self.lbl_vibe_status.setStyleSheet("color: #00E676; font-weight: bold; font-size: 13px;")

    def set_disconnected(self) -> None:
        self.lbl_vibe_status.setText("ROAD SURFACE: ACCELEROMETER DISCONNECTED")
        self.lbl_vibe_status.setStyleSheet("color: #FF334B; font-weight: bold; font-size: 13px;")
        self.lbl_calib_status.setText("CALIBRATION: SENSOR OFFLINE (WAITING FOR ESP32)")
        self.lbl_calib_status.setStyleSheet("color: #8B949E; font-size: 11px;")
