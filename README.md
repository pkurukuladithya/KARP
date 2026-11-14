# KARP — Kinetic Autonomous Recognition & Perception

<p align="center">
  <strong>GPU-Powered Distributed Advanced Driver Assistance System (ADAS) Prototype</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/GUI-PySide6%20(Qt6)-green.svg" alt="PySide6">
  <img src="https://img.shields.io/badge/AI-NVIDIA%20CUDA%20RTX%204050-76B900.svg" alt="CUDA">
  <img src="https://img.shields.io/badge/Edge-Raspberry%20Pi%204B-red.svg" alt="Raspberry Pi">
  <img src="https://img.shields.io/badge/Firmware-ESP32%20PlatformIO-E7352C.svg" alt="ESP32">
  <img src="https://img.shields.io/badge/License-MIT-purple.svg" alt="License">
</p>

---

## 1. Overview

**KARP** is a production-grade, distributed Advanced Driver Assistance System (ADAS) prototype designed to run across three dedicated hardware tiers:

1. **Laptop (AI Processing Engine)**: Equipped with an **NVIDIA RTX 4050 GPU (6 GB VRAM)**. Receives raw video from the vehicle camera over local Wi-Fi, executes deep neural network perception (lane detection, object detection, monocular distance estimation, traffic sign and light classification, object tracking), renders graphical overlays onto the footage, and streams the annotated video back to the vehicle edge unit.
2. **Raspberry Pi 4B (Edge Controller & HMI Host)**: Runs Raspberry Pi OS 64-bit Desktop connected to a front-facing USB camera, mini HDMI instrument cluster display, and the ESP32 microcontroller. Hosts a high-performance, dark-themed **PySide6** automotive dashboard.
3. **ESP32 (Sensor & Actuator Hub)**: Microcontroller interfaced to an I2C triaxial accelerometer and UART GPS module. Broadcasts validated telemetry packets to the Pi and triggers safety warning LEDs and audible buzzers.

```
       +-------------------------------------------------------------+
       |                       VEHICLE CABIN                         |
       |                                                             |
       |   [ Front Camera ] --------+                                |
       |                            | (USB 3.0)                      |
       |                            v                                |
       |   [ Mini HDMI ] <--- [ Raspberry Pi 4B ] <---> [ ESP32 ]    |
       |   (Instrument         (PySide6 HMI &            (Accel/GPS/ |
       |    Cluster)            Edge Host)                Buzzer)    |
       +----------------------------^--------------------------------+
                                    |
                        (Local Wi-Fi / Ethernet)
                   Dual Video Streams + JSON Telemetry
                                    |
       +----------------------------v--------------------------------+
       |                   CONCEALED LAPTOP UNIT                     |
       |       [ NVIDIA RTX 4050 GPU — CUDA AI Inference Engine ]     |
       +-------------------------------------------------------------+
```

---

## 2. Key Capabilities

- **Lane Detection & Lane Departure Warning (LDW)**: Real-time curve detection, lane center offset estimation, road curvature radius, and departure alert triggers.
- **Multi-Class Object Detection & Tracking**: Real-time identification of cars, trucks, buses, motorcycles, bicycles, pedestrians, traffic signs, and traffic lights with SORT-based tracking.
- **Calibrated Monocular Distance Estimation**: Approximate physical distance calculations based on camera horizon geometry and pinhole projection models (without fabricating unrealistic distances).
- **Traffic Sign & Traffic Light Recognition**: State detection (Red, Yellow, Green, Unknown) and classification of regulatory/warning road signs.
- **Road Condition & Vibration Estimation**: Digital high-pass filtering and dynamic RMS thresholding of triaxial accelerometer data to detect road roughness and potholes.
- **Interactive Vibration Threshold Sync**: Threshold can be modified on the PySide6 GUI and immediately synced to background filters and the ESP32.
- **Zero-Freeze PySide6 HMI**: Full multithreaded architecture (QThread workers for video, serial, telemetry) ensuring smooth 30 FPS rendering on the Pi.
- **Full Offline / Simulation Mode**: Built-in mock streams, GPS trajectory synthesizers, and accelerometer simulators for testing without physical vehicle hardware.

---

## 3. Repository Architecture

```
KARP/
├── README.md                      # System overview and quick start
├── .gitignore                     # Git ignore rules for Python, C++, weights
├── .env.example                   # Configuration environment variable templates
│
├── docs/                          # In-depth architectural & hardware documentation
│   ├── architecture.md            # Hardware topology & software design
│   ├── communication_protocol.md  # Wire schemas (Serial, WebSocket, Video)
│   ├── hardware_connections.md    # Pinouts, I2C addresses, level shifting
│   ├── installation.md            # Step-by-step setup for Laptop & Pi
│   ├── troubleshooting.md         # Diagnostic & network resolution guide
│   └── user_manual.md             # Operator dashboard navigation guide
│
├── shared/                        # Shared schemas & configuration
│   ├── config/                    # Centralized settings & persistence manager
│   └── protocols/                 # Packet framing, validation & JSON schemas
│
├── laptop_vision/                 # Laptop GPU Perception Service
│   ├── camera_receiver/           # Video stream demuxer & frame queue
│   ├── lane_detection/            # Polynomial & deep learning lane boundary fit
│   ├── object_detection/          # YOLO/ONNX object detector & distance estimator
│   ├── traffic_sign_detection/    # Regulatory sign classification
│   ├── traffic_light_detection/   # State classifier (Red/Yellow/Green)
│   ├── tracking/                  # SORT multi-target tracker
│   ├── decision_engine/           # TTC & Lane departure alert triggers
│   ├── video_encoder/             # Return annotated video broadcaster
│   ├── communication/             # WebSocket telemetry server
│   ├── models/                    # Model download instructions & weights
│   ├── main.py                    # AI service entry point
│   └── requirements.txt           # Laptop dependencies (PyTorch CUDA, ONNX, etc.)
│
├── raspberry_pi/                  # Raspberry Pi 4 HMI & Edge Service
│   ├── gui/                       # PySide6 Automotive Cluster Interface
│   │   ├── windows/               # Main application window & event loop
│   │   ├── widgets/               # Video render, gauges, charts, alert banners
│   │   ├── components/            # 7 Dashboard tabs
│   │   └── styles/                # Modern automotive dark theme stylesheet
│   ├── camera/                    # USB camera acquisition pipeline
│   ├── video_streaming/           # Low-latency Pi -> Laptop stream sender
│   ├── ai_receiver/               # Annotated video & telemetry receiver
│   ├── esp32_communication/       # Serial USB-UART parser & simulator
│   ├── sensor_processing/         # Accelerometer filtering & GPS processor
│   ├── system_monitor/            # System resource & FPS monitor
│   ├── config/                    # Pi local configuration manager
│   ├── main.py                    # HMI application entry point
│   └── requirements.txt           # Pi dependencies (PySide6, OpenCV, pyserial)
│
├── esp32_firmware/                # PlatformIO Embedded Firmware
│   ├── platformio.ini             # PlatformIO build configuration
│   ├── include/                   # Configurable pins, I2C addresses, protocol defs
│   ├── src/                       # Sensor drivers, NMEA parser, actuator control
│   └── README.md                  # Flashing and verification instructions
│
├── scripts/                       # Deployment, execution & simulation scripts
│   ├── setup_laptop.ps1           # Windows laptop automated installer
│   ├── setup_laptop.sh            # Linux laptop installer
│   ├── setup_pi.sh                # Raspberry Pi automated installer
│   ├── run_laptop.bat / .sh       # Launch AI service
│   ├── run_pi.sh                  # Launch Pi HMI
│   └── run_simulation.py / .bat   # Run complete system in simulation mode
│
└── tests/                         # Automated unit & integration tests
    ├── test_vision/               # Vision pipeline & annotation tests
    ├── test_communication/        # Video framing & WebSocket protocol tests
    ├── test_sensors/              # Accelerometer filtering & GPS parsing tests
    └── test_configuration/        # Configuration schema & persistence tests
```

---

## 4. Quick Start Guide

### Step 1: Clone Repository
```bash
git clone https://github.com/your-org/KARP.git
cd KARP
```

### Step 2: Running in Simulation Mode (No physical hardware required)
You can immediately evaluate the complete system (AI pipeline, PySide6 dashboard, simulated GPS track, and simulated road vibrations) on a single workstation:
```bash
python scripts/run_simulation.py
```

### Step 3: Deployment on Real Hardware
1. **Flash ESP32**:
   ```bash
   cd esp32_firmware && pio run --target upload
   ```
2. **Start Laptop AI Service**:
   ```bash
   python laptop_vision/main.py --host 0.0.0.0 --port 5000
   ```
3. **Start Raspberry Pi HMI**:
   ```bash
   python raspberry_pi/main.py --laptop-ip 192.168.1.100
   ```

---

## 5. Safety Disclaimer
KARP is a research, demonstration, and educational prototype. It does not control vehicle steering, throttle, or braking, and must not be used as an autonomous safety-critical driving system. Always maintain manual control of the vehicle.
