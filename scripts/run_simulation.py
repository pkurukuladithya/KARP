"""
Master Simulation & Demonstration Launcher for KARP ADAS.
Launches both the Laptop AI Perception Engine and the Raspberry Pi PySide6 HMI in simulation mode.
Provides full end-to-end evaluation without requiring physical camera, vehicle, or microcontroller hardware.
"""

from __future__ import annotations
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="KARP ADAS End-to-End Simulation Runner")
    parser.add_argument("--fullscreen", action="store_true", help="Launch PySide6 HMI in fullscreen kiosk mode")
    parser.add_argument("--force-cpu", action="store_true", help="Force laptop perception to run in CPU mode")
    args = parser.parse_args()

    python_exe = sys.executable

    print("==================================================================")
    print("           KARP ADAS — MASTER SIMULATION ENVIRONMENT              ")
    print("==================================================================")
    print("Architecture : Distributed Edge-AI Split (Dual Video Streams + WS)")
    print("AI Engine    : laptop_vision/main.py (Ports: 5000 RX, 5001 TX, 8765 WS)")
    print("Edge HMI     : raspberry_pi/main.py (PySide6 7-Tab Instrument Cluster)")
    print("Hardware Mode: SYNTHETIC SIMULATION (Virtual Road, Accel, GNSS)")
    print("==================================================================\n")

    # 1. Start Laptop AI Perception Service in background subprocess
    laptop_cmd = [
        python_exe,
        str(ROOT_DIR / "laptop_vision" / "main.py"),
        "--host", "127.0.0.1",
        "--port", "5000",
        "--target-ip", "127.0.0.1",
        "--target-port", "5001",
        "--ws-port", "8765",
    ]
    if args.force_cpu:
        laptop_cmd.append("--force-cpu")

    print("[1/2] Starting Laptop AI Perception Service...")
    laptop_proc = subprocess.Popen(
        laptop_cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Allow AI service to initialize socket listeners
    time.sleep(1.5)

    # 2. Start Raspberry Pi HMI in foreground
    pi_cmd = [
        python_exe,
        str(ROOT_DIR / "raspberry_pi" / "main.py"),
        "--laptop-ip", "127.0.0.1",
        "--simulation",
    ]
    if args.fullscreen:
        pi_cmd.append("--fullscreen")

    print("[2/2] Starting Raspberry Pi 4 Automotive Cluster HMI...")

    try:
        pi_proc = subprocess.run(pi_cmd, cwd=str(ROOT_DIR))
    except KeyboardInterrupt:
        print("\n[INFO] Interrupt received. Terminating all KARP services...")
    finally:
        print("[INFO] Shutting down Laptop AI Perception Service...")
        laptop_proc.terminate()
        try:
            laptop_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            laptop_proc.kill()
        print("[INFO] Simulation cleanly terminated.")


if __name__ == "__main__":
    main()
