"""
Threaded Serial Communication Client for ESP32-S3 Hardware.

Auto-detects USB CDC / UART port (/dev/ttyACM0, /dev/ttyUSB0, COM*),
streams 5 Hz sensor telemetry without blocking, and dispatches ADAS
buzzer / LED commands to the ESP32.
"""

from __future__ import annotations
import glob
import json
import logging
import platform
import queue
import sys
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger("pi_brain.esp32")


def find_serial_ports() -> List[str]:
    """Finds candidate ESP32 USB-UART / USB-CDC serial ports."""
    system = platform.system()
    if system == "Linux":
        # ESP32-S3 native USB CDC appears as /dev/ttyACM*, CP2102/CH340 as /dev/ttyUSB*
        ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
        return ports if ports else ["/dev/ttyACM0", "/dev/ttyUSB0"]
    elif system == "Windows":
        # Candidate COM ports on Windows
        return [f"COM{i}" for i in range(1, 21)]
    return ["/dev/ttyACM0"]


class Esp32Client:
    def __init__(self, port: str = "auto", baud_rate: int = 115200):
        self.requested_port = str(port)
        self.baud_rate = int(baud_rate)
        self.active_port: Optional[str] = None
        self.connected = False

        self._running = True
        self._lock = threading.Lock()
        self._tx_queue: queue.Queue = queue.Queue(maxsize=32)

        # Thread-safe snapshot of the latest received telemetry
        self._snapshot: Dict[str, Any] = {
            "connected": False,
            "gps_valid": False,
            "lat": None,
            "lon": None,
            "speed_kmh": 0.0,
            "satellites": 0,
            "heading_deg": 0.0,
            "altitude_m": 0.0,
            "ax": 0.0,
            "ay": 0.0,
            "az": 1.0,
            "vibration": 0.0,
            "vibration_peak": 0.0,
            "road": "DISCONNECTED",
            "pothole": False,
            "timestamp_ms": 0,
        }

        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="Esp32Serial")
        self._thread.start()

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns the latest atomic telemetry snapshot (zero-wait)."""
        with self._lock:
            return dict(self._snapshot)

    def send_alert(self, level: str = "CRITICAL", buzzer_ms: int = 400) -> None:
        """Sends an audible buzzer & visual LED alert command to the ESP32."""
        if not self.connected:
            return
        cmd = json.dumps({"cmd": "actuate", "level": level, "buzzer_ms": int(buzzer_ms)}) + "\n"
        try:
            self._tx_queue.put_nowait(cmd.encode("utf-8"))
        except queue.Full:
            pass

    def stop(self) -> None:
        self._running = False
        self._thread.join(timeout=1.0)

    # ------------------------------------------------------------- Internal Worker
    def _worker_loop(self) -> None:
        if serial is None:
            logger.warning("pyserial is not installed. ESP32 serial communication disabled.")
            return

        ser = None
        while self._running:
            # 1. Connect / Reconnect
            if ser is None or not ser.is_open:
                ser = self._connect()
                if ser is None:
                    time.sleep(1.5)
                    continue

            # 2. Write outgoing commands from queue
            while not self._tx_queue.empty():
                try:
                    payload = self._tx_queue.get_nowait()
                    ser.write(payload)
                    ser.flush()
                except Exception as e:
                    logger.debug(f"Serial write error: {e}")

            # 3. Read incoming JSON lines (non-blocking)
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("{") and line.endswith("}"):
                        self._parse_line(line)
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.warning(f"Serial communication error on {self.active_port}: {e}")
                if ser:
                    try:
                        ser.close()
                    except Exception:
                        pass
                ser = None
                self._set_connected(False)
                time.sleep(1.0)

        if ser and ser.is_open:
            try:
                ser.close()
            except Exception:
                pass
        self._set_connected(False)

    def _connect(self) -> Optional[serial.Serial]:
        ports_to_try = [self.requested_port] if self.requested_port != "auto" else find_serial_ports()
        for p in ports_to_try:
            if not self._running:
                return None
            try:
                s = serial.Serial(p, self.baud_rate, timeout=0.1)
                self.active_port = p
                self._set_connected(True)
                logger.info(f"Connected to ESP32 on {p} @ {self.baud_rate} baud")
                return s
            except Exception:
                continue
        return None

    def _set_connected(self, state: bool) -> None:
        self.connected = state
        with self._lock:
            self._snapshot["connected"] = state
            if not state:
                self._snapshot["road"] = "DISCONNECTED"

    def _parse_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except Exception:
            return

        if not isinstance(msg, dict):
            return

        # Handle boot / status message
        if "boot" in msg or "error" in msg:
            logger.info(f"ESP32 status: {line}")
            return

        with self._lock:
            snap = self._snapshot
            snap["connected"] = True
            snap["timestamp_ms"] = int(msg.get("timestamp_ms", time.time() * 1000))

            # GPS Telemetry
            gps_ok = bool(msg.get("gpsValid", False))
            snap["gps_valid"] = gps_ok
            if gps_ok and msg.get("lat") is not None and msg.get("lon") is not None:
                snap["lat"] = float(msg["lat"])
                snap["lon"] = float(msg["lon"])
                snap["speed_kmh"] = float(msg.get("speed", msg.get("rawSpeed", 0.0)))
                snap["heading_deg"] = float(msg.get("heading_deg", 0.0))
                snap["altitude_m"] = float(msg.get("altitude_m", 0.0))
            snap["satellites"] = int(msg.get("satellites", 0))

            # MPU6050 Accelerometer
            snap["ax"] = float(msg.get("ax", 0.0))
            snap["ay"] = float(msg.get("ay", 0.0))
            snap["az"] = float(msg.get("az", 1.0))
            snap["vibration"] = float(msg.get("vibration", 0.0))
            snap["vibration_peak"] = float(msg.get("vibrationPeak", 0.0))
            snap["road"] = str(msg.get("road", "UNKNOWN"))
            snap["pothole"] = bool(msg.get("potholeCandidate", False))
