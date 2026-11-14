#!/usr/bin/env bash
# Launch Laptop AI Perception Service on Linux
set -e
cd "$(dirname "$0")/.."

if [ -f ".env_laptop/bin/python" ]; then
    PYTHON_EXE=".env_laptop/bin/python"
else
    PYTHON_EXE="python3"
fi

echo "[INFO] Starting KARP Laptop Vision Engine..."
exec "$PYTHON_EXE" laptop_vision/main.py "$@"
