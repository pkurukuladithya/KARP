"""
USB serial link to the KARP ESP32-S3 sensor hub (esp32_firmware/src/main.cpp).

Wire protocol (115200 baud, one JSON object per line, "\\r\\n" terminated):

  ESP32 -> Pi
    {"boot":"ESP32_S3_STARTING"}                                   once after reset
    {"status":"CALIBRATING","message":"..."}                       MPU calibration start
    {"status":"CALIBRATION_COMPLETE","baseline":1.0123}            MPU calibration done
    {"error":"MPU6050_NOT_FOUND" | "MPU6050_CALIBRATION_FAILED" | "MPU_READ_FAILED"}
    {"type":"sensor_telemetry", ...}                               5 Hz (every 200 ms)

  Pi -> ESP32
    {"cmd":"actuate","level":"CRITICAL"|"WARNING","buzzer_ms":N}
      CRITICAL = red LED blinks 10 Hz, WARNING = steady yellow LED, for buzzer_ms+200 ms
      (500 ms when buzzer_ms is 0). buzzer_ms is capped at 2000 by the firmware.

"Connected" means telemetry actually arrived recently, not merely that a port opened.
"""

from __future__ import annotations
import glob
import json
import logging
import platform
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import serial  # pyserial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - reported at runtime
    serial = None
    list_ports = None

logger = logging.getLogger("pi_brain.esp32")

# USB vendor IDs of boards that carry an ESP32
ESP_USB_VIDS = {
    0x303A: "Espressif native USB (ESP32-S3)",
    0x10C4: "Silicon Labs CP210x",
    0x1A86: "WCH CH340/CH343",
    0x0403: "FTDI",
}

TELEMETRY_RATE_HZ = 5.0
STALE_AFTER_S = 1.5  # ~7 missed packets -> show sensors as offline
REOPEN_AFTER_S = 5.0  # no telemetry this long on an open port -> reopen it
PROBE_TIMEOUT_S = 7.0  # after opening, wait this long for the first line (reset + boot + MPU calibration ~4 s)
POTHOLE_HOLD_S = 3.0  # keep a pothole event visible this long
MAX_LINE = 4096


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return default if v is None else float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return default if v is None else int(v)
    except (TypeError, ValueError):
        return default


def find_serial_ports() -> List[str]:
    """Candidate ESP32 ports, known ESP32 USB bridges first."""
    known: List[str] = []
    other: List[str] = []
    if list_ports is not None:
        for p in list_ports.comports():
            if p.vid in ESP_USB_VIDS:
                known.append(p.device)
            elif p.vid is not None or "ttyACM" in p.device or "ttyUSB" in p.device:
                other.append(p.device)  # some other USB serial device
    if not known and not other and platform.system() == "Linux":
        other = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    return known + other


def describe_ports() -> List[str]:
    if list_ports is None:
        return ["(pyserial not installed)"]
    out = []
    for p in list_ports.comports():
        vid = f"{p.vid:04X}:{p.pid:04X}" if p.vid is not None else "----:----"
        tag = ESP_USB_VIDS.get(p.vid, "")
        out.append(f"{p.device:<14} {vid}  {p.description}  {('<- ' + tag) if tag else ''}")
    return out or ["(no serial ports found)"]


def empty_snapshot() -> Dict[str, Any]:
    return {
        "connected": False,  # telemetry received within STALE_AFTER_S
        "link": "NO PORT",  # NO PORT | WAITING | ONLINE | STALE | NO PYSERIAL
        "port": None,
        "rx_hz": 0.0,
        "age_s": None,  # seconds since the last telemetry packet
        "boot_count": 0,
        "calibration": "UNKNOWN",  # UNKNOWN | CALIBRATING | OK | FAILED
        "baseline_g": None,
        "last_error": None,
        # GPS (NEO-6M)
        "gps_connected": False,  # NMEA bytes arriving from the module
        "gps_valid": False,  # fresh position fix
        "lat": None,
        "lon": None,
        "altitude_m": 0.0,
        "heading_deg": 0.0,
        "speed_kmh": 0.0,  # 0 unless the vehicle is confirmed moving
        "raw_speed_kmh": 0.0,
        "satellites": 0,
        # MPU6050
        "mpu_connected": False,
        "ax": 0.0,
        "ay": 0.0,
        "az": 0.0,
        "accel_g": 0.0,
        "vibration": 0.0,
        "vibration_peak": 0.0,
        "road": "DISCONNECTED",
        "confidence": 0,
        "vehicle_moving": False,
        "vehicle_state": "UNKNOWN",
        # Events / actuators
        "pothole": False,  # a pothole was reported within POTHOLE_HOLD_S
        "pothole_count": 0,
        "buzzer_on": False,
        "esp_timestamp_ms": 0,
    }


class Esp32Client:
    """Background serial reader/writer. Never blocks the caller."""

    def __init__(
        self,
        port: str = "auto",
        baud_rate: int = 115200,
        opener: Optional[Callable[[str, int], Any]] = None,
        autostart: bool = True,
    ):
        self.requested_port = str(port or "auto")
        self.baud_rate = int(baud_rate)
        self._opener = opener or self._open_port
        self._running = True
        self._lock = threading.Lock()
        self._tx_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=16)
        self._snap = empty_snapshot()
        self._last_rx = 0.0  # perf_counter of the last telemetry packet
        self._last_pothole = -1e9
        self._rx_count = 0
        self._rx_t0 = time.perf_counter()
        self._buf = bytearray()
        self.lines_ok = 0
        self.lines_bad = 0
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="Esp32Serial")
        if autostart:
            self._thread.start()

    # ------------------------------------------------------------------ public API
    @property
    def connected(self) -> bool:
        return self._last_rx > 0 and time.perf_counter() - self._last_rx < STALE_AFTER_S

    def get_telemetry(self) -> Dict[str, Any]:
        now = time.perf_counter()
        with self._lock:
            snap = dict(self._snap)
        age = now - self._last_rx if self._last_rx else None
        snap["age_s"] = age
        snap["connected"] = age is not None and age < STALE_AFTER_S
        if snap["link"] == "ONLINE" and not snap["connected"]:
            snap["link"] = "STALE"
        if not snap["connected"]:
            snap["road"] = "DISCONNECTED"
        snap["pothole"] = now - self._last_pothole < POTHOLE_HOLD_S
        return snap

    def send_actuate(self, level: str, buzzer_ms: int = 0) -> bool:
        """Queues {"cmd":"actuate"} for the firmware. Returns False if the ESP32 is offline."""
        if not self.connected:
            return False
        payload = {"cmd": "actuate", "level": str(level), "buzzer_ms": int(max(0, min(2000, buzzer_ms)))}
        try:
            self._tx_queue.put_nowait((json.dumps(payload, separators=(",", ":")) + "\n").encode("ascii"))
            return True
        except queue.Full:
            return False

    # Backwards compatible name
    def send_alert(self, level: str = "CRITICAL", buzzer_ms: int = 400) -> bool:
        return self.send_actuate(level, buzzer_ms)

    def stop(self) -> None:
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.5)

    # ------------------------------------------------------------------ parsing
    def feed(self, data: bytes) -> None:
        """Feeds raw serial bytes; complete lines are parsed (partial lines are kept)."""
        self._buf += data
        while True:
            nl = self._buf.find(b"\n")
            if nl < 0:
                break
            raw = bytes(self._buf[:nl])
            del self._buf[: nl + 1]
            self._handle_line(raw)
        if len(self._buf) > MAX_LINE:  # garbage without newlines
            self._buf.clear()
            self.lines_bad += 1

    def _handle_line(self, raw: bytes) -> None:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            return
        if not line.startswith("{"):
            logger.debug(f"ESP32 text: {line[:120]}")  # e.g. ROM boot banner after reset
            return
        try:
            msg = json.loads(line)
        except ValueError:
            self.lines_bad += 1
            return
        if not isinstance(msg, dict):
            self.lines_bad += 1
            return
        self.lines_ok += 1
        try:
            self.handle_message(msg)
        except Exception as e:  # a bad field must never kill the link
            self.lines_bad += 1
            logger.debug(f"Unparseable ESP32 message ({e}): {line[:200]}")

    def handle_message(self, msg: Dict[str, Any]) -> None:
        if msg.get("type") == "sensor_telemetry":
            self._apply_telemetry(msg)
        elif "boot" in msg:
            logger.info(f"ESP32 booted ({msg['boot']})")
            with self._lock:
                self._snap["boot_count"] += 1
                self._snap["calibration"] = "UNKNOWN"
        elif "status" in msg:
            status = str(msg["status"])
            logger.info(f"ESP32 status: {status}" + (f" baseline={msg['baseline']} g" if "baseline" in msg else ""))
            with self._lock:
                if status == "CALIBRATING":
                    self._snap["calibration"] = "CALIBRATING"
                elif status == "CALIBRATION_COMPLETE":
                    self._snap["calibration"] = "OK"
                    self._snap["baseline_g"] = _f(msg.get("baseline"), 1.0)
        elif "error" in msg:
            err = str(msg["error"])
            logger.warning(f"ESP32 error: {err}")
            with self._lock:
                self._snap["last_error"] = err
                if "CALIBRATION" in err:
                    self._snap["calibration"] = "FAILED"
        else:
            logger.debug(f"ESP32 message ignored: {msg}")

    def _apply_telemetry(self, m: Dict[str, Any]) -> None:
        now = time.perf_counter()
        gps_valid = bool(m.get("gpsValid", False)) and m.get("lat") is not None and m.get("lon") is not None
        act = m.get("actuators") if isinstance(m.get("actuators"), dict) else {}
        pothole = bool(m.get("potholeCandidate", False))
        with self._lock:
            s = self._snap
            s["link"] = "ONLINE"
            s["esp_timestamp_ms"] = _i(m.get("timestamp_ms"))
            s["gps_connected"] = bool(m.get("gpsConnected", False))
            s["gps_valid"] = gps_valid
            if gps_valid:
                s["lat"] = _f(m.get("lat"))
                s["lon"] = _f(m.get("lon"))
                s["altitude_m"] = _f(m.get("altitude_m"))
                s["heading_deg"] = _f(m.get("heading_deg"))
            s["speed_kmh"] = _f(m.get("speed"))
            s["raw_speed_kmh"] = _f(m.get("rawSpeed"))
            s["satellites"] = _i(m.get("satellites"))
            s["mpu_connected"] = bool(m.get("mpuConnected", False))
            s["ax"], s["ay"], s["az"] = _f(m.get("ax")), _f(m.get("ay")), _f(m.get("az"))
            s["accel_g"] = _f(m.get("acceleration"))
            if m.get("baseline") is not None:
                s["baseline_g"] = _f(m.get("baseline"))
            s["vibration"] = _f(m.get("vibration"))
            s["vibration_peak"] = _f(m.get("vibrationPeak"))
            s["road"] = str(m.get("road") or "UNKNOWN")
            s["confidence"] = _i(m.get("confidence"))
            s["vehicle_moving"] = bool(m.get("vehicleMoving", False))
            s["vehicle_state"] = str(m.get("vehicleState") or "UNKNOWN")
            s["buzzer_on"] = bool(act.get("buzzer", False))
            if s["calibration"] == "UNKNOWN" and s["mpu_connected"]:
                s["calibration"] = "OK"  # Pi started after the ESP32 had already booted
            if pothole:
                s["pothole_count"] += 1
            self._rx_count += 1
            dt = now - self._rx_t0
            if dt >= 2.0:
                s["rx_hz"] = self._rx_count / dt
                self._rx_count, self._rx_t0 = 0, now
        if pothole:
            self._last_pothole = now
        self._last_rx = now

    # ------------------------------------------------------------------ serial worker
    def _open_port(self, port: str, baud: int):
        if "://" in port:  # e.g. socket://127.0.0.1:7000 (tools/esp32_emulator.py)
            return serial.serial_for_url(port, baudrate=baud, timeout=0.05, write_timeout=0.5)
        kwargs = {"baudrate": baud, "timeout": 0.05, "write_timeout": 0.5}
        if platform.system() != "Windows":
            kwargs["exclusive"] = True  # never share the port with another reader
        return serial.Serial(port, **kwargs)

    def _set_link(self, link: str, port: Optional[str] = None) -> None:
        with self._lock:
            self._snap["link"] = link
            self._snap["port"] = port

    def _worker_loop(self) -> None:
        if serial is None and self._opener == self._open_port:
            logger.error("pyserial is not installed -> ESP32 disabled. Fix: pip install pyserial")
            self._set_link("NO PYSERIAL")
            return

        last_warn = 0.0
        while self._running:
            candidates = [self.requested_port] if self.requested_port != "auto" else find_serial_ports()
            if not candidates:
                self._set_link("NO PORT")
                if time.perf_counter() - last_warn > 15:
                    logger.warning("ESP32 not found (no USB serial ports). Plug it in; retrying...")
                    last_warn = time.perf_counter()
                self._sleep(2.0)
                continue

            for port in candidates:
                if not self._running:
                    break
                self._session(port)
            self._sleep(1.0)

        self._set_link("NO PORT")

    def _session(self, port: str) -> None:
        """Opens one port and serves it until it fails or goes silent."""
        try:
            ser = self._opener(port, self.baud_rate)
        except Exception as e:
            msg = str(e)
            if "Permission denied" in msg or "PermissionError" in type(e).__name__:
                logger.error(f"No permission for {port}. Fix: sudo usermod -aG dialout $USER  (then reboot)")
            elif "busy" in msg.lower() or "lock" in msg.lower() or "Access is denied" in msg:
                logger.warning(f"{port} is in use by another program (serial monitor / raspberry_pi/main.py?)")
            else:
                logger.debug(f"Cannot open {port}: {e}")
            return

        logger.info(f"Opened {port} @ {self.baud_rate} - waiting for ESP32 data...")
        self._set_link("WAITING", port)
        self._buf.clear()
        opened = time.perf_counter()
        got_data = False
        try:
            while self._running:
                # 1. Outgoing commands
                while True:
                    try:
                        ser.write(self._tx_queue.get_nowait())
                    except queue.Empty:
                        break

                # 2. Incoming bytes (blocks at most the port timeout)
                chunk = ser.read(max(1, getattr(ser, "in_waiting", 0) or 0))
                if chunk:
                    before = self._last_rx
                    self.feed(chunk)
                    if self._last_rx != before and not got_data:
                        got_data = True
                        logger.info(f"ESP32 ONLINE on {port} (telemetry {TELEMETRY_RATE_HZ:.0f} Hz)")

                # 3. Watchdogs
                now = time.perf_counter()
                if not got_data:
                    if now - opened > PROBE_TIMEOUT_S:
                        logger.info(f"No ESP32 telemetry on {port} within {PROBE_TIMEOUT_S:.0f} s - trying next port")
                        return
                elif now - self._last_rx > REOPEN_AFTER_S:
                    logger.warning(f"ESP32 on {port} silent for {REOPEN_AFTER_S:.0f} s - reopening")
                    return
        except Exception as e:
            logger.warning(f"ESP32 link on {port} lost: {e}")
        finally:
            try:
                ser.close()
            except Exception:
                pass
            with self._lock:
                self._snap["link"] = "NO PORT"

    def _sleep(self, s: float) -> None:
        end = time.perf_counter() + s
        while self._running and time.perf_counter() < end:
            time.sleep(0.05)


class AlertSignaler:
    """
    Turns the Pi's ADAS alerts into ESP32 LED/buzzer commands, rate-limited.

      CRITICAL : red LED blinks + beep-beep (re-sent every 0.4 s while active)
      WARNING  : steady yellow LED (refreshed every 0.4 s), one short beep when it starts
      nothing  : no commands; the firmware's override expires by itself within 0.5 s
    """

    PERIOD_S = 0.4

    def __init__(self, client: Esp32Client):
        self.client = client
        self._last_send = 0.0
        self._last_level: Optional[str] = None
        self._warn_keys: set = set()

    def update(self, alerts, now: Optional[float] = None, beep_keys_exclude=("pothole",)) -> Optional[str]:
        now = time.perf_counter() if now is None else now
        levels = {a.level for a in alerts}
        level = "CRITICAL" if "CRITICAL" in levels else ("WARNING" if "WARNING" in levels else None)
        warn_keys = {a.key for a in alerts if a.level == "WARNING" and a.key not in beep_keys_exclude}
        new_warning = bool(warn_keys - self._warn_keys)
        self._warn_keys = warn_keys

        if level is None:
            self._last_level = None
            return None
        changed = level != self._last_level
        if not changed and not new_warning and now - self._last_send < self.PERIOD_S:
            return None

        if level == "CRITICAL":
            buzzer = 200
        else:
            buzzer = 150 if (new_warning or changed and warn_keys) else 0
        if self.client.send_actuate(level, buzzer):
            self._last_send, self._last_level = now, level
            return level
        return None
