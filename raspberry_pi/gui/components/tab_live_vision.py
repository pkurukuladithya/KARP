"""
Tab 2 — Live Vision Component.
Enlarged perception feed with detailed detection table and AI inference diagnostics.
"""

from typing import List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSlider,
)
from raspberry_pi.gui.widgets.video_widget import VideoWidget
from shared.protocols.message_schemas import DetectedObject, TrafficSignData


class TabLiveVision(QWidget):
    confidence_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Left: Large Video Widget (70% width)
        left_layout = QVBoxLayout()
        self.video_widget = VideoWidget(title="Enlarged ADAS Deep Learning Stream")
        left_layout.addWidget(self.video_widget)
        main_layout.addLayout(left_layout, stretch=70)

        # Right: AI Metadata & Object Table (30% width)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)

        # AI Engine Diagnostics Card
        perf_card = QFrame()
        perf_card.setProperty("card", True)
        perf_layout = QGridLayout(perf_card)

        self.lbl_device = QLabel("INFERENCE DEVICE: NVIDIA RTX 4050")
        self.lbl_device.setStyleSheet("color: #00D2FF; font-weight: bold;")
        self.lbl_fps = QLabel("INFERENCE FPS: 0.0")
        self.lbl_latency = QLabel("LATENCY: 0.0 ms")
        self.lbl_dropped = QLabel("DROPPED FRAMES: 0")

        perf_layout.addWidget(self.lbl_device, 0, 0, 1, 2)
        perf_layout.addWidget(self.lbl_fps, 1, 0)
        perf_layout.addWidget(self.lbl_latency, 1, 1)
        perf_layout.addWidget(self.lbl_dropped, 2, 0, 1, 2)
        right_layout.addWidget(perf_card)

        # Confidence Threshold Slider Card
        thresh_card = QFrame()
        thresh_card.setProperty("card", True)
        thresh_layout = QVBoxLayout(thresh_card)

        self.lbl_conf = QLabel("AI CONFIDENCE THRESHOLD: 45%")
        self.slider_conf = QSlider(Qt.Horizontal)
        self.slider_conf.setRange(10, 95)
        self.slider_conf.setValue(45)
        self.slider_conf.valueChanged.connect(self._on_slider_conf_changed)

        thresh_layout.addWidget(self.lbl_conf)
        thresh_layout.addWidget(self.slider_conf)
        right_layout.addWidget(thresh_card)

        # Tracked Objects Table
        table_card = QFrame()
        table_card.setProperty("card", True)
        table_layout = QVBoxLayout(table_card)
        table_title = QLabel("TRACKED TARGETS")
        table_title.setStyleSheet("font-weight: bold; color: #F0F6FC;")
        table_layout.addWidget(table_title)

        self.table_objects = QTableWidget(0, 4)
        self.table_objects.setHorizontalHeaderLabels(["ID", "Class", "Conf", "Dist (m)"])
        self.table_objects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_objects.setStyleSheet("""
            QTableWidget {
                background-color: #0D1117;
                border: 1px solid #30363D;
                gridline-color: #21262D;
            }
            QHeaderView::section {
                background-color: #161B22;
                color: #8B949E;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #21262D;
            }
        """)
        table_layout.addWidget(self.table_objects)
        right_layout.addWidget(table_card)

        main_layout.addLayout(right_layout, stretch=30)

    def _on_slider_conf_changed(self, value: int) -> None:
        conf = value / 100.0
        self.lbl_conf.setText(f"AI CONFIDENCE THRESHOLD: {value}%")
        self.confidence_changed.emit(conf)

    def update_diagnostics(self, device: str, fps: float, latency_ms: float, dropped: int) -> None:
        self.lbl_device.setText(f"INFERENCE DEVICE: {device}")
        self.lbl_fps.setText(f"INFERENCE FPS: {fps:.1f}")
        self.lbl_latency.setText(f"LATENCY: {latency_ms:.1f} ms")
        self.lbl_dropped.setText(f"DROPPED FRAMES: {dropped}")

    def update_objects_table(self, objects: List[DetectedObject]) -> None:
        self.table_objects.setRowCount(len(objects))
        for row, obj in enumerate(objects):
            self.table_objects.setItem(row, 0, QTableWidgetItem(f"#{obj.id}"))
            self.table_objects.setItem(row, 1, QTableWidgetItem(obj.class_name.upper()))
            self.table_objects.setItem(row, 2, QTableWidgetItem(f"{obj.confidence*100:.0f}%"))
            dist_str = f"{obj.estimated_distance_m:.1f}m" if obj.estimated_distance_m is not None else "--"
            self.table_objects.setItem(row, 3, QTableWidgetItem(dist_str))
