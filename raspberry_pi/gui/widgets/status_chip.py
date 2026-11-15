"""
Status Chip / Pill Indicator Widget for Automotive Dashboard.
Displays status icon, label, and state (Connected, Disconnected, Warning, Sim).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget
from raspberry_pi.gui.styles.style_utils import set_style


class StatusChip(QWidget):
    STATE_OK = "ok"
    STATE_WARN = "warn"
    STATE_ERROR = "error"
    STATE_SIM = "sim"

    COLOR_MAP = {
        STATE_OK: QColor(0, 230, 118),       # Bright Green
        STATE_WARN: QColor(255, 183, 3),     # Safety Amber
        STATE_ERROR: QColor(255, 51, 75),    # Critical Red
        STATE_SIM: QColor(0, 210, 255),      # Neon Cyan
    }

    def __init__(self, title: str, initial_text: str = "OFFLINE", initial_state: str = STATE_ERROR, parent=None):
        super().__init__(parent)
        self._title = title
        self._text = initial_text
        self._state = initial_state

        self.setFixedHeight(30)
        self.setMinimumWidth(130)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        self.label = QLabel(f"{self._title}: {self._text}")
        self.label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self.label.setFont(font)
        layout.addWidget(self.label)

        self._update_style()

    def set_status(self, text: str, state: str) -> None:
        if self._text != text:
            self._text = text
            self.label.setText(f"{self._title}: {self._text}")
        if self._state != state:
            # Restyle only when the colour state changes (stylesheets are expensive on the Pi)
            self._state = state
            self._update_style()

    def _update_style(self) -> None:
        color = self.COLOR_MAP.get(self._state, QColor(139, 148, 158)).name()
        set_style(self, f"""
            QWidget {{
                background-color: #161B22;
                border: 1px solid {color};
                border-radius: 14px;
            }}
            QLabel {{
                color: {color};
                border: none;
                background: transparent;
            }}
        """)
