#!/usr/bin/env bash
# Linux Laptop Automated Environment Setup Script
set -e

echo "=========================================================="
echo "         KARP ADAS — Linux Laptop Setup                   "
echo "=========================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.10-3.12."
    exit 1
fi

echo "[INFO] Detected Python: $(python3 --version)"

# Check for nvidia-smi
if command -v nvidia-smi &> /dev/null; then
    echo "[SUCCESS] NVIDIA GPU Detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "[WARNING] nvidia-smi not found. CPU fallback will be active."
fi

# Create virtual environment
VENV_DIR=".env_laptop"
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 || true
pip install -r laptop_vision/requirements.txt

echo "[INFO] Verifying PyTorch and CUDA..."
python3 -c "import torch; print('PyTorch:', torch.__version__, '| CUDA:', torch.cuda.is_available())" || true

echo "[INFO] Ensuring all shell scripts are executable..."
chmod +x "$(dirname "$0")"/*.sh 2>/dev/null || chmod +x scripts/*.sh 2>/dev/null || true

echo "Setup Complete! Run with: ./scripts/run_laptop.sh"
