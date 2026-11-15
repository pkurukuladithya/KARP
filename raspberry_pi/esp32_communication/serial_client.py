"""
Threaded Serial Communication Worker for ESP32 Microcontroller.
Handles non-blocking line-delimited JSON streaming, automatic reconnection, and command dispatch.
"""

from __future__ import annotations
import json
import logging
import queue
import time
from typing import Optional
from PySide6.QtCore import QThread, Signal

import serial
from shared.protocols.framing import JsonLineCodec
from shared.protocols.message_schemas import SensorTelemetry, ThresholdCommand, ActuatorCommand

logger = logging.getLogger("KARP.SerialClient")


class Esp32SerialWorker(QThread):
    telemetry_received = Signal(object)  # SensorTelemetry
    connection_changed = Signal(bool)
    log_message = Signal(str)

    def __init__(self, port: str = "/dev/ttyUSB0", baud_rate: int = 115200, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud_rate = baud_rate
        self._running = True
        self._tx_queue: queue.Queue = queue.Queue()
        self._codec = JsonLineCodec()

    def stop(self) -> None:
        self._running = False
        self.wait(1000)

    def send_threshold(self, threshold_g: float) -> None:
        cmd = ThresholdCommand(threshold_g=threshold_g).to_json() + "\n"
        self._tx_queue.put(cmd.encode("utf-8"))

    def send_actuator_cmd(self, led: Optional[bool] = None, buzzer_ms: Optional[int] = None) -> None:
        cmd = ActuatorCommand(led=led, buzzer_duration_ms=buzzer_ms).to_json() + "\n"
        self._tx_queue.put(cmd.encode("utf-8"))

    def run(self) -> None:
        ser: Optional[serial.Serial] = None
        is_connected = False

        while self._running:
            # 1. Connect if not connected
            if ser is None or not ser.is_open:
                try:
                    ser = serial.Serial(self.port, self.baud_rate, timeout=0.1)
                    is_connected = True
                    self.connection_changed.emit(True)
                    self.log_message.emit(f"[SERIAL] Connected to ESP32 on {self.port} @ {self.baud_rate} baud")
                except Exception as e:
                    if is_connected:
                        is_connected = False
                        self.connection_changed.emit(False)
                        self.log_message.emit(f"[SERIAL] Connection lost to {self.port}: {e}")
                    time.sleep(1.5)
                    continue

            # 2. Transmit queued commands
            while not self._tx_queue.empty():
                try:
                    out_bytes = self._tx_queue.get_nowait()
                    ser.write(out_bytes)
                    ser.flush()
                except Exception as e:
                    logger.warning(f"Failed to write to serial: {e}")

            # 3. Read incoming bytes
            try:
                waiting = ser.in_waiting
                if waiting > 0:
                    raw_chunk = ser.read(waiting)
                    lines = self._codec.feed(raw_chunk)
                    for line in lines:
                        self._process_line(line)
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.warning(f"Serial read error: {e}")
                ser.close()
                ser = None
                is_connected = False
                self.connection_changed.emit(False)
                time.sleep(1.0)

        if ser and ser.is_open:
            ser.close()
        self.connection_changed.emit(False)

    def _process_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except Exception:
            self.log_message.emit(f"[SERIAL RAW] {line}")
            return
        if not isinstance(msg, dict):
            return
        msg_type = msg.get("type")
        if msg_type == "sensor_telemetry":
            self.telemetry_received.emit(SensorTelemetry.from_dict(msg))
        else:
            # ack / boot_status / other: log only, never treat as sensor data
            self.log_message.emit(f"[ESP32 {msg_type}] {line}")
