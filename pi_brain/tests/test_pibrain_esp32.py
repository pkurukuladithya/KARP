"""
Pi <-> ESP32 serial protocol tests. Messages are byte-for-byte what
esp32_firmware/src/main.cpp prints (ArduinoJson serializeJson + Serial.println -> "\\r\\n").
"""

import json
import threading
import time

import pytest

from brain import esp32 as esp
from brain.alerts import Alert
from brain.esp32 import AlertSignaler, Esp32Client

BOOT = [
    b'{"boot":"ESP32_S3_STARTING"}\r\n',
    b'{"status":"CALIBRATING","message":"Keep MPU6050 still"}\r\n',
    b'{"status":"CALIBRATION_COMPLETE","baseline":1.0123}\r\n',
]


def telemetry(fix=True, pothole=False, ts=1000) -> bytes:
    """Same key order / formatting as outputJSON() in the firmware."""
    lat = "6.927079" if fix else "null"
    lon = "79.861244" if fix else "null"
    s = (
        '{"type":"sensor_telemetry","timestamp_ms":%d,"gpsConnected":true,"gpsValid":%s,'
        '"lat":%s,"lon":%s,"altitude_m":%s,"heading_deg":%s,"speed":%s,"rawSpeed":%s,"satellites":%d,'
        '"mpuConnected":true,"ax":0.012,"ay":-0.004,"az":1.008,"acceleration":1.008,"baseline":1.012,'
        '"vibration":0.021,"vibrationPeak":%s,"road":"%s","confidence":%d,"potholeCandidate":%s,'
        '"vehicleMoving":%s,"vehicleState":"%s","actuators":{"buzzer":%s,"led":"%s"}}\r\n'
    ) % (
        ts, "true" if fix else "false", lat, lon,
        "12.3" if fix else "0", "87.5" if fix else "0",
        "42.5" if fix else "0", "42.5" if fix else "0", 8 if fix else 3,
        "0.41" if pothole else "0.05", "ROUGH" if pothole else "SMOOTH", 65 if pothole else 90,
        "true" if pothole else "false", "true" if fix else "false", "MOVING" if fix else "STATIONARY",
        "true" if pothole else "false", "ROUGH" if pothole else "SMOOTH",
    )
    json.loads(s)  # the fixture itself must be valid JSON
    return s.encode()


def client() -> Esp32Client:
    return Esp32Client("test", autostart=False)


def test_full_telemetry_is_decoded():
    c = client()
    for line in BOOT:
        c.feed(line)
    c.feed(telemetry(fix=True))
    t = c.get_telemetry()
    assert t["connected"] and t["link"] == "ONLINE"
    assert t["gps_valid"] and t["lat"] == pytest.approx(6.927079) and t["lon"] == pytest.approx(79.861244)
    assert t["speed_kmh"] == 42.5 and t["satellites"] == 8 and t["heading_deg"] == 87.5
    assert t["mpu_connected"] and t["az"] == pytest.approx(1.008) and t["road"] == "SMOOTH"
    assert t["calibration"] == "OK" and t["baseline_g"] == pytest.approx(1.012)
    assert t["boot_count"] == 1 and c.lines_bad == 0


def test_status_messages_do_not_overwrite_telemetry():
    c = client()
    c.feed(telemetry(fix=True))
    c.feed(BOOT[1])  # a "status" line used to reset GPS/MPU values to defaults
    t = c.get_telemetry()
    assert t["gps_valid"] and t["speed_kmh"] == 42.5 and t["road"] == "SMOOTH"


def test_lines_split_across_reads_are_reassembled():
    c = client()
    data = b"".join(BOOT) + telemetry(ts=1) + telemetry(ts=2)
    for i in range(0, len(data), 7):  # USB delivers arbitrary chunks
        c.feed(data[i : i + 7])
    assert c.get_telemetry()["esp_timestamp_ms"] == 2
    assert c.lines_bad == 0 and c.lines_ok == 5


def test_no_fix_keeps_last_position_but_reports_invalid():
    c = client()
    c.feed(telemetry(fix=True))
    c.feed(telemetry(fix=False))
    t = c.get_telemetry()
    assert not t["gps_valid"] and t["satellites"] == 3 and t["speed_kmh"] == 0.0


def test_garbage_and_boot_banner_are_ignored():
    c = client()
    c.feed(b"ESP-ROM:esp32s3-20210327\r\nBuild:Mar 27 2021\r\n{bad json\r\n\xff\xfe\r\n")
    c.feed(telemetry())
    assert c.get_telemetry()["connected"]


def test_wrong_field_types_do_not_break_the_link():
    c = client()
    c.feed(b'{"type":"sensor_telemetry","gpsValid":true,"lat":"x","lon":null,"satellites":"?","ax":null}\r\n')
    c.feed(telemetry())
    assert c.get_telemetry()["satellites"] == 8


def test_pothole_event_is_latched(monkeypatch):
    c = client()
    c.feed(telemetry(pothole=True))
    c.feed(telemetry(pothole=False))
    t = c.get_telemetry()
    assert t["pothole"] and t["pothole_count"] == 1
    c._last_pothole -= esp.POTHOLE_HOLD_S + 0.1
    assert not c.get_telemetry()["pothole"]


def test_goes_stale_without_data():
    c = client()
    c.feed(telemetry())
    c._last_rx -= esp.STALE_AFTER_S + 0.1
    t = c.get_telemetry()
    assert not t["connected"] and t["link"] == "STALE" and t["road"] == "DISCONNECTED"


def test_actuate_command_matches_firmware_parser():
    c = client()
    assert not c.send_actuate("CRITICAL", 200)  # offline -> nothing is queued
    c.feed(telemetry())
    assert c.send_actuate("CRITICAL", 5000)
    cmd = c._tx_queue.get_nowait()
    assert cmd.endswith(b"\n") and len(cmd) < 512  # firmware drops lines > 512 chars
    msg = json.loads(cmd)
    assert msg == {"cmd": "actuate", "level": "CRITICAL", "buzzer_ms": 2000}


def test_alert_signaler_rate_limits_and_beeps_once_for_warnings():
    c = client()
    c.feed(telemetry())
    sig = AlertSignaler(c)
    crit = [Alert("fcw", "CRITICAL", "BRAKE")]
    sent = [sig.update(crit, now=t / 100) for t in range(0, 100)]  # 1 s at 100 Hz
    assert sent.count("CRITICAL") == 3  # every 0.4 s, not every frame
    while not c._tx_queue.empty():
        c._tx_queue.get_nowait()

    warn = [Alert("ldw", "WARNING", "LANE")]
    sig.update([], now=5.0)
    sig.update(warn, now=5.1)
    sig.update(warn, now=5.6)
    first, second = (json.loads(c._tx_queue.get_nowait()) for _ in range(2))
    assert first["level"] == "WARNING" and first["buzzer_ms"] == 150
    assert second["buzzer_ms"] == 0  # LED refresh only, no repeated beeping

    sig.update([], now=6.0)
    sig.update([Alert("pothole", "WARNING", "POTHOLE")], now=6.1)
    assert json.loads(c._tx_queue.get_nowait())["buzzer_ms"] == 0  # the ESP32 already beeped


class FakeSerial:
    """Behaves like pyserial.Serial fed by the firmware."""

    def __init__(self, chunks, close_after=None):
        self._data = bytearray(b"".join(chunks))
        self.written = []
        self.is_open = True
        self._lock = threading.Lock()

    @property
    def in_waiting(self):
        return len(self._data)

    def push(self, b):
        with self._lock:
            self._data += b

    def read(self, n=1):
        with self._lock:
            out = bytes(self._data[:n])
            del self._data[:n]
        if not out:
            time.sleep(0.01)
        return out

    def write(self, b):
        self.written.append(b)
        return len(b)

    def close(self):
        self.is_open = False


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_worker_reads_port_and_writes_commands():
    fake = FakeSerial(BOOT + [telemetry()])
    c = Esp32Client("/dev/ttyACM0", opener=lambda port, baud: fake)
    try:
        assert _wait(lambda: c.connected)
        t = c.get_telemetry()
        assert t["port"] == "/dev/ttyACM0" and t["gps_valid"]
        assert c.send_actuate("WARNING", 150)
        assert _wait(lambda: fake.written)
        assert json.loads(fake.written[0])["level"] == "WARNING"
    finally:
        c.stop()


def test_worker_skips_silent_port_and_reopens(monkeypatch):
    monkeypatch.setattr(esp, "PROBE_TIMEOUT_S", 0.3)
    opened = []

    def opener(port, baud):
        opened.append(port)
        if len(opened) == 1:
            return FakeSerial([])  # wrong device: never sends anything
        return FakeSerial([telemetry()])

    c = Esp32Client("/dev/ttyACM0", opener=opener)
    try:
        assert _wait(lambda: c.connected, timeout=4.0)
        assert len(opened) >= 2
    finally:
        c.stop()


def test_worker_survives_open_errors():
    def opener(port, baud):
        raise PermissionError("[Errno 13] Permission denied: '/dev/ttyACM0'")

    c = Esp32Client("/dev/ttyACM0", opener=opener)
    time.sleep(0.2)
    assert not c.connected and c._thread.is_alive()
    c.stop()
