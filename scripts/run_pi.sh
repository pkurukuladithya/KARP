#!/usr/bin/env bash
# Launch Raspberry Pi PySide6 HMI Application
set -e
cd "$(dirname "$0")/.."

# Auto-configure DISPLAY for HDMI mini display if not already set (e.g. over SSH)
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    export DISPLAY=:0
fi

if [ -f ".env_pi/bin/python" ]; then
    PYTHON_EXE=".env_pi/bin/python"
else
    PYTHON_EXE="python3"
fi

echo "=========================================================="
echo "    KARP ADAS — Raspberry Pi 4 Instrument Cluster HMI     "
echo "=========================================================="
echo "[INFO] Launching PySide6 Automotive Cluster..."
echo "[INFO] Standalone Graceful Fallback Active: Works with or without"
echo "       physical camera, ESP32, or Laptop AI connected."
echo "=========================================================="

exec "$PYTHON_EXE" raspberry_pi/main.py "$@"
