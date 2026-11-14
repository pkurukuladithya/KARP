#!/usr/bin/env bash
# Launch Raspberry Pi PySide6 HMI Application
set -e
cd "$(dirname "$0")/.."

if [ -f ".env_pi/bin/python" ]; then
    PYTHON_EXE=".env_pi/bin/python"
else
    PYTHON_EXE="python3"
fi

echo "[INFO] Starting KARP PySide6 Instrument Cluster HMI..."
exec "$PYTHON_EXE" raspberry_pi/main.py "$@"
