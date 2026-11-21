#!/usr/bin/env bash
# One-time setup of KARP Pi Brain on a Raspberry Pi 4B (Raspberry Pi OS 64-bit, Bookworm).
#   cd ~/KARP/pi_brain && chmod +x setup_pi.sh run.sh && ./setup_pi.sh
set -e
cd "$(dirname "$0")"

echo "== KARP Pi Brain setup =="
ARCH="$(uname -m)"
if [ "$ARCH" != "aarch64" ]; then
  echo "WARNING: this is a $ARCH (32-bit) OS. onnxruntime/ncnn need 64-bit Raspberry Pi OS."
  echo "         It will still run with the slow OpenCV backend. Reinstall 64-bit OS for full speed."
fi

echo "-- System packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip v4l-utils libgl1 || true
# CSI camera support (harmless if you use a USB webcam)
sudo apt-get install -y python3-picamera2 || true

echo "-- Python virtual environment (.venv)"
# --system-site-packages lets the venv see apt's picamera2
python3 -m venv --system-site-packages .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install ncnn || echo "(ncnn wheel not available - ONNX Runtime will be used)"

echo "-- ESP32 serial access (USB)"
if ! id -nG "$USER" | grep -qw dialout; then
  sudo usermod -aG dialout "$USER"
  echo "Added $USER to the 'dialout' group for /dev/ttyACM*/ttyUSB*. REBOOT once before running."
fi
python tools/esp32_monitor.py --list || true

echo "-- Model files"
if [ ! -f models/yolo11n_320.onnx ] && [ ! -f models/yolo11n_320_ncnn/model.ncnn.param ]; then
  echo "ERROR: no model in pi_brain/models. Run on the laptop: python pi_brain/tools/export_model.py, then git pull."
  exit 1
fi

echo "-- Benchmark on this Pi"
python tools/benchmark.py --runs 10

echo
echo "Setup complete. Start with:  ./run.sh"
