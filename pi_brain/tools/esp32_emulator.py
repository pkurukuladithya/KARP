"""
ESP32 firmware emulator for testing pi_brain WITHOUT the real board.

Speaks exactly the protocol of esp32_firmware/src/main.cpp over TCP, so pyserial
can open it as a port:

    python tools/esp32_emulator.py                     # listens on 127.0.0.1:7000
    python main.py --esp-port socket://127.0.0.1:7000  # in another terminal

Prints every command the Pi sends (LED / buzzer). Emits a pothole event every 10 s.
"""

from __future__ import annotations
import argparse
import json
import math
import socket
import threading
import time


def telemetry(t0: float, pothole: bool, fix_after: float = 3.0) -> dict:
    t = time.time() - t0
    fix = t > fix_after  # GPS "searching" until then
    return {
        "type": "sensor_telemetry",
        "timestamp_ms": int(t * 1000),
        "gpsConnected": True,
        "gpsValid": fix,
        "lat": round(6.9271 + t * 1e-5, 6) if fix else None,
        "lon": round(79.8612 + t * 1e-5, 6) if fix else None,
        "altitude_m": 12.0 if fix else 0.0,
        "heading_deg": 45.0 if fix else 0.0,
        "speed": round(40 + 5 * math.sin(t / 5), 1) if fix else 0.0,
        "rawSpeed": round(40 + 5 * math.sin(t / 5), 1) if fix else 0.0,
        "satellites": 8 if fix else 2,
        "mpuConnected": True,
        "ax": 0.01, "ay": -0.02, "az": 1.0, "acceleration": 1.0, "baseline": 1.0,
        "vibration": 0.08 if pothole else 0.02,
        "vibrationPeak": 0.42 if pothole else 0.06,
        "road": "ROUGH" if pothole else "SMOOTH",
        "confidence": 65 if pothole else 90,
        "potholeCandidate": pothole,
        "vehicleMoving": fix,
        "vehicleState": "MOVING" if fix else "STATIONARY",
        "actuators": {"buzzer": pothole, "led": "ROUGH" if pothole else "SMOOTH"},
    }


def serve(conn: socket.socket, fix_after: float = 3.0) -> None:
    t0 = time.time()

    def send(obj) -> None:
        conn.sendall((json.dumps(obj, separators=(",", ":")) + "\r\n").encode())

    def reader() -> None:
        buf = b""
        while True:
            try:
                data = conn.recv(1024)
            except OSError:
                return
            if not data:
                return
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                print(f"   <- from Pi: {line.decode(errors='replace').strip()}")

    threading.Thread(target=reader, daemon=True).start()
    send({"boot": "ESP32_S3_STARTING"})
    send({"status": "CALIBRATING", "message": "Keep MPU6050 still"})
    time.sleep(1.0)
    send({"status": "CALIBRATION_COMPLETE", "baseline": 1.0012})
    n = 0
    while True:
        n += 1
        send(telemetry(t0, pothole=(n % 50 == 0), fix_after=fix_after))  # pothole every 10 s
        time.sleep(0.2)  # 5 Hz like the firmware


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7000)
    ap.add_argument("--fix-after", type=float, default=3.0, help="Seconds of GPS searching before a fix")
    args = ap.parse_args()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen(1)
    print(f"ESP32 emulator on socket://127.0.0.1:{args.port}")
    while True:
        conn, _ = srv.accept()
        print("Pi connected")
        try:
            serve(conn, args.fix_after)
        except OSError:
            print("Pi disconnected")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
