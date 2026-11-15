"""
Dynamic Warning & Alert Banner Widget.
Updates in real-time based on ADAS perception and sensor alerts.
"""

from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from raspberry_pi.gui.styles.style_utils import set_style


class AlertBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AlertBanner")
        self.setFixedHeight(46)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)

        self.icon_label = QLabel("🛡")
        icon_font = QFont()
        icon_font.setPointSize(16)
        self.icon_label.setFont(icon_font)
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("ALL SYSTEMS OPERATIONAL — ADAS ACTIVE")
        text_font = QFont()
        text_font.setPointSize(12)
        text_font.setBold(True)
        text_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        self.text_label.setFont(text_font)
        self.text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self.text_label, stretch=1)

        self._flash_state = False
        self._current_level = "NORMAL"

        self.set_alert("ALL SYSTEMS OPERATIONAL", "NORMAL")

    def set_alert(self, message: str, level: str = "NORMAL") -> None:
        self._current_level = level.upper()
        self.text_label.setText(message.upper())

        if self._current_level == "CRITICAL":
            self.icon_label.setText("⚠")
            set_style(self, """
                QFrame#AlertBanner {
                    background-color: #4D0A12;
                    border: 2px solid #FF334B;
                    border-radius: 6px;
                }
                QLabel {
                    color: #FF6B7D;
                    font-weight: bold;
                }
            """)
        elif self._current_level == "WARNING":
            self.icon_label.setText("⚡")
            set_style(self, """
                QFrame#AlertBanner {
                    background-color: #3D2C04;
                    border: 2px solid #FFB703;
                    border-radius: 6px;
                }
                QLabel {
                    color: #FFD166;
                    font-weight: bold;
                }
            """)
        elif self._current_level == "INFO":
            self.icon_label.setText("ℹ")
            set_style(self, """
                QFrame#AlertBanner {
                    background-color: #05263B;
                    border: 1px solid #00D2FF;
                    border-radius: 6px;
                }
                QLabel {
                    color: #00D2FF;
                }
            """)
        else:
            self.icon_label.setText("✔")
            set_style(self, """
                QFrame#AlertBanner {
                    background-color: #092B1B;
                    border: 1px solid #00E676;
                    border-radius: 6px;
                }
                QLabel {
                    color: #00E676;
                }
            """)
