# KARP ADAS — System Architecture Specification

## 1. Executive Summary & Design Philosophy
**KARP** (Kinetic Autonomous Recognition & Perception) is a distributed, real-time Advanced Driver Assistance System designed with an edge-cloud split computing paradigm:
- **Vehicle Edge Controller & HMI (Raspberry Pi 4B)**: Interfaces directly with vehicle sensors (ESP32 via USB serial), camera video acquisition, HDMI touchscreen/display driver, and the Qt6/PySide6 automotive instrument cluster UI.
- **High-Performance AI Processor (NVIDIA RTX 4050 Laptop)**: Physically concealed in the vehicle; hosts deep learning perception pipelines (Lane Detection, Object Detection, Monocular Distance Estimation, Traffic Sign/Light Classification, Tracking, and Collision Warning Decision Engine).
- **Embedded Sensor Hub (ESP32)**: Dedicated real-time microcontroller reading high-frequency triaxial accelerometer data (I2C) and NMEA GPS data (UART), driving vehicle warning hardware (piezo buzzers, status LEDs).

---

## 2. Distributed Hardware Topology

```
+---------------------------------------------------------------------------------+
|                                VEHICLE CABIN                                    |
|                                                                                 |
|   +-----------------------+                    +----------------------------+   |
|   |  Mini HDMI Display    |                    |  Front-Facing USB Camera   |   |
|   +-----------^-----------+                    +--------------+-------------+   |
|               |                                               |                 |
|               | (HDMI Video Out)                              | (V4L2 / UVC)    |
|   +-----------+-----------------------------------------------v-------------+   |
|   |                     RASPBERRY PI 4B (Edge & HMI Host)                   |   |
|   |  * PySide6 Automotive Cluster GUI (7 Nav Tabs, Dark Theme, Kiosk Mode) |   |
|   |  * Low-Latency Stream Sender (Pi -> Laptop: 720p @ 30 FPS)              |   |
|   |  * Stream Receiver & Frame Decoder (Laptop -> Pi Annotated Video)       |   |
|   |  * ESP32 Serial Frame Parser & Road Vibration Event Classifier          |   |
|   |  * Dynamic Configuration & Vibration Threshold Sync                     |   |
|   +-------------^---------------------------------------------+-------------+   |
|                 | (USB Serial /dev/ttyUSB0)                   |                 |
|                 |                                             |                 |
|   +-------------v-------------+                               |                 |
|   |     ESP32 SENSOR HUB      |                               |                 |
|   |  * I2C: Triaxial Accel    |                               | (Local Wi-Fi    |
|   |  * UART: NMEA GPS         |                               |  Dual Video     |
|   |  * GPIO: LEDs & Buzzer    |                               |  Streams + WS)  |
|   +---------------------------+                               |                 |
+---------------------------------------------------------------|-----------------+
                                                                |
                                                                v
+---------------------------------------------------------------------------------+
|                        CONCEALED LAPTOP AI CO-PROCESSOR                         |
|                                                                                 |
|   +-------------------------------------------------------------------------+   |
|   |                 NVIDIA GeForce RTX 4050 (6GB VRAM)                      |   |
|   |  * Hardware Accelerated H.264 RTP/UDP / TCP Video Stream Demuxer        |   |
|   |  * CUDA/TensorRT/ONNX-Runtime Object Detection (COCO 80 / Traffic subset) |
|   |  * Modular Polynomial / Deep Polynomial Curve Lane Boundary Detector    |   |
|   |  * Calibrated Monocular Distance Estimator (Pin-Hole & Horizon Model)   |   |
|   |  * Colorimetric & Spatial Traffic Light State Classifier                |   |
|   |  * Traffic Sign Classifier (Speed Limit, Stop, Yield, Crosswalk)        |   |
|   |  * Multi-Object SORT Tracking (IoU + Kalman Filter)                     |   |
|   |  * Lane Departure Warning (LDW) & Forward Collision Warning (FCW)       |   |
|   |  * Annotated Frame Compositor & H.264 Return Stream Broadcaster         |   |
|   |  * Real-Time Telemetry & Metric WebSocket Dispatcher                    |   |
|   +-------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------+
```

---

## 3. Communication Architecture & Data Flow

KARP implements strict segregation between heavy video transport and lightweight asynchronous telemetry:

### 3.1 Primary Video Transports (Bidirectional)
1. **Direction A (Camera Feed: Pi -> Laptop)**:
   - Captures frames from USB camera using OpenCV / GStreamer pipeline.
   - Encodes into low-latency compressed frames (H.264 / JPEG over UDP/RTP with fallback to TCP socket streamer).
   - Laptop receives into a bounded queue (`maxlen=2`) with frame-dropping policy to maintain sub-50ms glass-to-glass latency.
2. **Direction B (Annotated Visual Stream: Laptop -> Pi)**:
   - Laptop renders lane polygons, bounding boxes, distance overlays, sign cards, and warning HUD.
   - Encodes annotated frames and streams to Raspberry Pi port `5001`.
   - Raspberry Pi GUI decodes frames in a dedicated QThread and delivers `QImage` to the OpenGL-backed video viewport via Qt signals.

### 3.2 Metadata & Telemetry Transport (WebSocket / TCP)
- Port: `8765`
- Direction: Bidirectional JSON messaging.
- Laptop sends detection bounding boxes, lane departure metrics, inference latency, and warning states.
- Raspberry Pi sends heartbeat, configuration changes (e.g. confidence thresholds), and user control events.

### 3.3 Microcontroller Transport (ESP32 <-> Raspberry Pi)
- Hardware: USB-UART CDC Serial (`115200` baud).
- Framing: Delimited JSON packets (`\n`), validated by CRC checksum / structured schema.
- ESP32 broadcasts sensor telemetry at 20 Hz (`{"type":"sensor_data", "accel":{...}, "gps":{...}}`).
- Pi sends threshold updates and actuator triggers (`{"type":"set_threshold", "val": 2.5}`).

---

## 4. Software Subsystems & Design Patterns

### 4.1 Raspberry Pi HMI Subsystem
- **Framework**: PySide6 (Qt for Python).
- **Threading Model**:
  - `Main GUI Thread`: Pure event loop and QPainter / widget rendering. Zero I/O blocking.
  - `VideoWorker (QThread)`: Network frame socket listener, H.264/JPEG decoder, frame dropping.
  - `SerialWorker (QThread)`: Non-blocking serial port polling, packet framing, JSON parsing.
  - `TelemetryWorker (QThread)`: WebSocket client for AI metadata and latency counters.
  - `RoadConditionProcessor`: Decoupled digital filter (high-pass/band-pass), dynamic gravity compensation, dynamic RMS vibration calculation.

### 4.2 Laptop Vision Subsystem
- **Engine**: Modular Pipeline Pattern (`PipelineOrchestrator`).
  - `LaneDetector`: Modular interface supporting sliding-window polynomial fitting and deep learning lane segmentation.
  - `ObjectDetector`: Modular interface supporting YOLOv8/v11 (ONNX Runtime, PyTorch CUDA, CPU fallback).
  - `SignDetector & TrafficLightClassifier`: Crop-and-classify spatial pipelines.
  - `SortTracker`: Fast multi-target tracking to prevent box flickering.
  - `AdasDecisionEngine`: Evaluates Time-To-Collision (TTC) and Lane Departure offset.
  - `VisualAnnotator`: High-performance OpenCV drawing overlay with color-coded safety tiers.

### 4.3 ESP32 Firmware Subsystem
- **Framework**: PlatformIO + Arduino Core for ESP32.
- **Architecture**: Cooperative non-blocking state machine with FreeRTOS tasks:
  - Task 1: Sensor polling (I2C MPU6050/ADXL345 at 50 Hz, UART GPS NMEA at 10 Hz).
  - Task 2: Command listening, LED heartbeat, piezo PWM buzzer safety watchdog (auto shutoff after max 1.5s).
