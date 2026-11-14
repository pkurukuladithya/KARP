# KARP Installation & Environment Setup Guide

This guide provides step-by-step instructions for deploying KARP on both the **NVIDIA Laptop** and the **Raspberry Pi 4**, as well as flashing the **ESP32 Firmware**.

---

## 1. Laptop Setup (Windows / Linux + NVIDIA GPU)

### Prerequisites
- Python 3.10 - 3.12 (64-bit)
- NVIDIA RTX 4050 (or any CUDA-compatible GPU) with latest NVIDIA Game Ready / Studio Drivers
- Git

### Automated Installation (Windows PowerShell)
Run the automated installation script from the project root:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_laptop.ps1
```

### Manual Installation
1. Create and activate a dedicated virtual environment:
   ```cmd
   python -m venv .env_laptop
   .env_laptop\Scripts\activate
   ```
2. Install PyTorch with CUDA 12.1/12.4 support:
   ```cmd
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
   ```
3. Install laptop vision dependencies:
   ```cmd
   pip install -r laptop_vision/requirements.txt
   ```
4. Verify CUDA detection:
   ```cmd
   python -c "import torch; print('CUDA Available:', torch.cuda.is_available(), 'GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
   ```

---

## 2. Raspberry Pi 4 Setup (Raspberry Pi OS 64-bit Desktop)

### Prerequisites
- Raspberry Pi 4B running Debian Bookworm 64-bit Desktop
- Connected USB camera (`/dev/video0`)
- Connected ESP32 via USB (`/dev/ttyUSB0`)

### Automated Installation (Linux Bash)
```bash
chmod +x scripts/setup_pi.sh
./scripts/setup_pi.sh
```

### Manual Installation
1. Install system multimedia and Qt dependencies:
   ```bash
   sudo apt-get update
   sudo apt-get install -y python3-pip python3-venv libgl1-mesa-dev libglib2.0-0 \
       gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
       gstreamer1.0-plugins-bad v4l-utils
   ```
2. Add your user to the dialout and video groups:
   ```bash
   sudo usermod -a -G dialout,video $USER
   ```
3. Create and activate virtual environment:
   ```bash
   python3 -m venv .env_pi --system-site-packages
   source .env_pi/bin/activate
   ```
4. Install Python dependencies:
   ```bash
   pip install -r raspberry_pi/requirements.txt
   ```

---

## 3. ESP32 Firmware Flashing (PlatformIO)

### Prerequisites
- VSCode with PlatformIO IDE extension OR PlatformIO CLI installed (`pip install platformio`)

### Flashing via CLI
1. Open a terminal in `esp32_firmware`:
   ```bash
   cd esp32_firmware
   pio run --target upload
   ```
2. To monitor serial output:
   ```bash
   pio device monitor --baud 115200
   ```
