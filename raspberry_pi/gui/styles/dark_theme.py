"""
Automotive Dark Theme Stylesheet for KARP ADAS PySide6 HMI.
Colors:
- Deep Cabin Background: #0D1117 / #161B22
- Surface Card: #21262D
- Card Border: #30363D
- Neon Accent / Primary: #00D2FF
- Safety Amber / Warning: #FFB703
- Alert Red / Critical: #FF334B
- Safe Green: #00E676
- Text Primary: #F0F6FC
- Text Muted: #8B949E
"""

DARK_THEME_QSS = """
QMainWindow {
    background-color: #0A0D12;
    color: #F0F6FC;
    font-family: 'Segoe UI', 'Ubuntu', 'Roboto', sans-serif;
}

QWidget {
    background-color: transparent;
    color: #F0F6FC;
    font-size: 13px;
}

/* Card Panels */
QFrame[card="true"] {
    background-color: #161B22;
    border: 1px solid #30363D;
    border-radius: 8px;
    padding: 10px;
}

/* Header Bar */
QFrame#HeaderBar {
    background-color: #12161E;
    border-bottom: 2px solid #00D2FF;
    padding: 6px 16px;
}

QLabel#HeaderTitle {
    color: #00D2FF;
    font-size: 20px;
    font-weight: bold;
    letter-spacing: 2px;
}

QLabel#HeaderSubtitle {
    color: #8B949E;
    font-size: 11px;
}

/* Tab Bar Styling */
QTabWidget::pane {
    border: 1px solid #21262D;
    background-color: #0D1117;
    border-radius: 6px;
    margin-top: -1px;
}

QTabBar::tab {
    background-color: #161B22;
    color: #8B949E;
    padding: 10px 22px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    border: 1px solid #21262D;
    border-bottom: none;
}

QTabBar::tab:selected {
    background-color: #21262D;
    color: #00D2FF;
    border-bottom: 3px solid #00D2FF;
}

QTabBar::tab:hover:!selected {
    background-color: #1C2128;
    color: #C9D1D9;
}

/* Push Buttons */
QPushButton {
    background-color: #21262D;
    color: #F0F6FC;
    border: 1px solid #30363D;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #30363D;
    border-color: #8B949E;
}

QPushButton:pressed {
    background-color: #00D2FF;
    color: #0A0D12;
}

QPushButton#PrimaryButton {
    background-color: #0077B6;
    border: 1px solid #00D2FF;
    color: #FFFFFF;
}

QPushButton#PrimaryButton:hover {
    background-color: #0096C7;
}

QPushButton#DangerButton {
    background-color: #9E2A2B;
    border: 1px solid #E63946;
    color: #FFFFFF;
}

QPushButton#DangerButton:hover {
    background-color: #D62828;
}

/* Sliders */
QSlider::groove:horizontal {
    border: 1px solid #30363D;
    height: 6px;
    background: #161B22;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #00D2FF;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #F0F6FC;
    border: 1px solid #00D2FF;
    width: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #00D2FF;
}

/* Inputs and Spinboxes */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0D1117;
    border: 1px solid #30363D;
    border-radius: 5px;
    padding: 6px 10px;
    color: #F0F6FC;
    selection-background-color: #00D2FF;
    selection-color: #0A0D12;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #00D2FF;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #0D1117;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #30363D;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #00D2FF;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Text Displays / Logs */
QTextEdit, QPlainTextEdit {
    background-color: #0D1117;
    border: 1px solid #30363D;
    border-radius: 6px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    color: #00E676;
    padding: 8px;
}
"""
