#!/usr/bin/env bash
# Raspberry Pi 4B Automated Environment Setup Script
# Designed for Raspberry Pi OS 64-bit Desktop
set -e

echo "=========================================================="
echo "         KARP ADAS — Raspberry Pi 4 Setup                 "
echo "=========================================================="

echo "[INFO] Updating APT repositories and installing system libraries..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    libgl1-mesa-dev \
    libglib2.0-0 \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    v4l-utils

echo "[INFO] Granting dialout & video group permissions for $USER..."
sudo usermod -a -G dialout,video $USER || true

echo "[INFO] Ensuring all shell scripts are executable..."
chmod +x "$(dirname "$0")"/*.sh 2>/dev/null || chmod +x scripts/*.sh 2>/dev/null || true

VENV_DIR=".env_pi"
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating virtual environment in $VENV_DIR with system site packages..."
    python3 -m venv "$VENV_DIR" --system-site-packages
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel
pip install -r raspberry_pi/requirements.txt

echo "[INFO] Verifying PySide6 and OpenCV..."
python3 -c "import PySide6, cv2, serial; print('PySide6:', PySide6.__version__, '| OpenCV:', cv2.__version__, '| PySerial:', serial.__version__)"

echo "=========================================================="
echo "Setup Complete! Note: If you modified groups, please reboot"
echo "or run 'newgrp dialout' before connecting the ESP32."
echo "Launch HMI with: ./scripts/run_pi.sh"
echo "=========================================================="
