"""
Check the Pi <-> ESP32 USB serial link on its own (no camera / AI needed).

    python tools/esp32_monitor.py --list            # show serial ports (ESP32 boards are marked)
    python tools/esp32_monitor.py                   # auto-detect, print decoded telemetry every second
    python tools/esp32_monitor.py --port /dev/ttyACM0
    python tools/esp32_monitor.py --test-actuators  # also blink LEDs + beep: WARNING, then CRITICAL
    python tools/esp32_monitor.py --raw             # print every raw line from the ESP32 too
"""

from __future__ import annotations
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brain.esp32 import Esp32Client, describe_ports  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="KARP ESP32 serial link monitor")
    ap.add_argument("--port", default="auto")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--list", action="store_true", help="List serial ports and exit")
    ap.add_argument("--test-actuators", action="store_true", help="Send WARNING then CRITICAL commands")
    ap.add_argument("--raw", action="store_true", help="Also print raw lines")
    ap.add_argument("--seconds", type=float, default=0, help="Stop after N seconds (0 = until Ctrl+C)")
    args = ap.parse_args()

    print("Serial ports:")
    for line in describe_ports():
        print("  " + line)
    if args.list:
        return 0

    logging.basicConfig(level=logging.DEBUG if args.raw else logging.INFO,
                        format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    client = Esp32Client(args.port, args.baud)
    if args.raw:
        orig = client._handle_line

        def show(raw: bytes) -> None:
            print("RAW  " + raw.decode("utf-8", "replace").rstrip())
            orig(raw)

        client._handle_line = show

    t0 = time.perf_counter()
    tested = False
    try:
        while not args.seconds or time.perf_counter() - t0 < args.seconds:
            time.sleep(1.0)
            t = client.get_telemetry()
            if not t["connected"]:
                age = f", last data {t['age_s']:.1f} s ago" if t["age_s"] is not None else ""
                print(f"[{t['link']}] port={t['port']}{age}")
                continue
            gps = (f"FIX {t['lat']:.6f},{t['lon']:.6f} alt {t['altitude_m']:.0f} m hdg {t['heading_deg']:.0f}"
                   if t["gps_valid"] else ("searching" if t["gps_connected"] else "NO NMEA DATA (check GPS wiring)"))
            print(
                f"[ONLINE {t['port']} {t['rx_hz']:.1f} Hz] "
                f"GPS {gps} sats {t['satellites']} speed {t['speed_kmh']:.1f} (raw {t['raw_speed_kmh']:.1f}) km/h | "
                f"MPU {'OK' if t['mpu_connected'] else 'ERROR'} a=({t['ax']:+.2f},{t['ay']:+.2f},{t['az']:+.2f}) g "
                f"vib {t['vibration']:.3f}/{t['vibration_peak']:.3f} g | road {t['road']} {t['confidence']}% "
                f"{t['vehicle_state']} | potholes {t['pothole_count']} | calib {t['calibration']}"
            )
            if args.test_actuators and not tested:
                tested = True
                print(">> WARNING: yellow LED + short beep")
                client.send_actuate("WARNING", 150)
                time.sleep(1.5)
                print(">> CRITICAL: red LED blinking + beeps (2 s)")
                for _ in range(5):
                    client.send_actuate("CRITICAL", 200)
                    time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
    print(f"lines ok {client.lines_ok}, bad {client.lines_bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
