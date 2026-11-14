"""
Tab 6 — Hardware Control Component.
Diagnostic controls for ESP32 actuators, buzzer watchdog testing, and serial log console.
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton,
    QTextEdit,
)


class TabHardware(QWidget):
    actuator_cmd = Signal(dict)  # {"led": bool, "buzzer_duration_ms": int}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._led_state = False
        self._buzzer_active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Top Grid: Hardware Link Status
        status_card = QFrame()
        status_card.setProperty("card", True)
        status_layout = QGridLayout(status_card)

        title = QLabel("EMBEDDED HARDWARE PERIPHERAL STATUS")
        title.setStyleSheet("color: #00D2FF; font-weight: bold; font-size: 14px;")
        status_layout.addWidget(title, 0, 0, 1, 3)

        self.lbl_esp32_status = QLabel("ESP32 Controller: CONNECTED (/dev/ttyUSB0)")
        self.lbl_i2c_status = QLabel("I2C Accelerometer: DETECTED (0x68)")
        self.lbl_uart_status = QLabel("UART GPS: DETECTED (9600 Baud)")

        self.lbl_esp32_status.setStyleSheet("color: #00E676; font-weight: bold;")
        self.lbl_i2c_status.setStyleSheet("color: #00E676; font-weight: bold;")
        self.lbl_uart_status.setStyleSheet("color: #00E676; font-weight: bold;")

        status_layout.addWidget(self.lbl_esp32_status, 1, 0)
        status_layout.addWidget(self.lbl_i2c_status, 1, 1)
        status_layout.addWidget(self.lbl_uart_status, 1, 2)
        layout.addWidget(status_card)

        # Middle Grid: Actuator Controls & Safety Safeguards
        ctrl_card = QFrame()
        ctrl_card.setProperty("card", True)
        ctrl_layout = QGridLayout(ctrl_card)
        ctrl_layout.setSpacing(10)

        ctrl_title = QLabel("ACTUATOR DEMONSTRATION & SAFETY WATCHDOG")
        ctrl_title.setStyleSheet("color: #F0F6FC; font-weight: bold;")
        ctrl_layout.addWidget(ctrl_title, 0, 0, 1, 3)

        # LED Toggle Button
        self.btn_led = QPushButton("Toggle Warning LED (GPIO 2)")
        self.btn_led.clicked.connect(self._on_toggle_led)
        ctrl_layout.addWidget(self.btn_led, 1, 0)

        # Buzzer Test Pulse Button
        self.btn_buzzer = QPushButton("Pulse Audible Buzzer (300 ms)")
        self.btn_buzzer.setObjectName("DangerButton")
        self.btn_buzzer.clicked.connect(self._on_pulse_buzzer)
        ctrl_layout.addWidget(self.btn_buzzer, 1, 1)

        # Safety Note
        lbl_safety = QLabel("WATCHDOG: Firmware automatically forces buzzer OFF after max 1.5 seconds.")
        lbl_safety.setStyleSheet("color: #8B949E; font-size: 11px;")
        ctrl_layout.addWidget(lbl_safety, 1, 2)

        layout.addWidget(ctrl_card)

        # Bottom Grid: Microcontroller Serial Log Console
        log_card = QFrame()
        log_card.setProperty("card", True)
        log_layout = QVBoxLayout(log_card)

        log_title = QLabel("ESP32 FRAMED SERIAL COMMUNICATION LOG")
        log_title.setStyleSheet("color: #8B949E; font-weight: bold;")
        log_layout.addWidget(log_title)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        log_layout.addWidget(self.log_console)

        layout.addWidget(log_card, stretch=1)

    def _on_toggle_led(self) -> None:
        self._led_state = not self._led_state
        self.btn_led.setText(f"Warning LED (GPIO 2): {'ACTIVE (ON)' if self._led_state else 'OFF'}")
        self.actuator_cmd.emit({"led": self._led_state})
        self.append_log(f"[TX] Command -> Set LED: {self._led_state}")

    def _on_pulse_buzzer(self) -> None:
        self.actuator_cmd.emit({"buzzer_duration_ms": 300})
        self.append_log("[TX] Command -> Pulse Buzzer: 300ms (Safe Auto-Shutoff)")

    def append_log(self, text: str) -> None:
        self.log_console.append(text)
        # Keep maximum lines to avoid unbounded memory consumption
        if self.log_console.document().lineCount() > 200:
            cursor = self.log_console.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def update_hardware_status(self, esp_connected: bool, i2c_ok: bool, gps_ok: bool) -> None:
        if esp_connected:
            self.lbl_esp32_status.setText("ESP32 Controller: CONNECTED")
            self.lbl_esp32_status.setStyleSheet("color: #00E676; font-weight: bold;")
        else:
            self.lbl_esp32_status.setText("ESP32 Controller: DISCONNECTED")
            self.lbl_esp32_status.setStyleSheet("color: #FF334B; font-weight: bold;")

        if i2c_ok:
            self.lbl_i2c_status.setText("I2C Accelerometer: OPERATIONAL")
            self.lbl_i2c_status.setStyleSheet("color: #00E676; font-weight: bold;")
        else:
            self.lbl_i2c_status.setText("I2C Accelerometer: NO RESPONSE")
            self.lbl_i2c_status.setStyleSheet("color: #FFB703; font-weight: bold;")

        if gps_ok:
            self.lbl_uart_status.setText("UART GPS: RECEIVING NMEA")
            self.lbl_uart_status.setStyleSheet("color: #00E676; font-weight: bold;")
        else:
            self.lbl_uart_status.setText("UART GPS: WAITING FOR DATA")
            self.lbl_uart_status.setStyleSheet("color: #FFB703; font-weight: bold;")
