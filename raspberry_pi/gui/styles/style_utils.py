"""
Stylesheet helpers.

QWidget.setStyleSheet() re-polishes the widget (and its children) against the
application stylesheet every time it is called - even with identical CSS. On a
Raspberry Pi 4 that costs milliseconds per call; calling it at video/telemetry
rate (30 Hz) saturates the GUI thread and makes the whole HMI lag.
set_style() only applies the stylesheet when it actually changes.
"""

from PySide6.QtWidgets import QWidget


def set_style(widget: QWidget, css: str) -> None:
    if widget.styleSheet() != css:
        widget.setStyleSheet(css)
