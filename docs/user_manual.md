# KARP User & Operator Manual

## 1. Starting the System

### In a Real Vehicle / Testbench Setup:
1. **Power Up ESP32**: Plug ESP32 into Raspberry Pi USB port. The blue power LED lights up.
2. **Power Up Raspberry Pi 4**: Connect the USB-C power supply. The mini HDMI display will boot into the desktop.
3. **Start Laptop AI Engine**:
   - Open terminal on Laptop:
     ```cmd
     scripts\run_laptop.bat
     ```
   - The laptop service starts listening on port `5000` (video reception), `5001` (annotated video broadcast), and `8765` (telemetry WebSocket).
4. **Start Raspberry Pi HMI**:
   - On the Raspberry Pi desktop:
     ```bash
     ./scripts/run_pi.sh
     ```
   - The PySide6 automotive dashboard will launch fullscreen in dark mode.

---

## 2. Navigating the 7 Dashboard Tabs

### Tab 1 — Overview
The primary driver instrument cluster. Displays:
- Central annotated road feed with lane overlays and warning HUD.
- Speedometer gauge (derived from GPS velocity).
- Mini vehicle status cards (AI Link, ESP32 status, GPS Fix, Road Roughness index).
- Active high-priority safety alert banner (e.g. "LANE DEPARTURE WARNING" in bright red).

### Tab 2 — Live Vision
Full-screen enlarged perception view:
- Color-coded lane boundaries (Green = in lane, Red = departure).
- Bounding boxes with object class labels, confidence %, and estimated distance in meters.
- Recognized traffic signs (speed limit badges, stop signs) and traffic light state indicator.
- Real-time performance diagnostics: Inference FPS, Reception FPS, End-to-end Latency (ms), and GPU utilization.

### Tab 3 — Vehicle Sensors
Detailed sensor telemetry:
- Live numeric displays for Accelerometer (Ax, Ay, Az, Magnitude).
- Live numeric displays for GPS (Latitude, Longitude, Altitude, Satellites, Speed, Fix Status).
- Dynamic refresh frequency counters.

### Tab 4 — GPS Location
Vehicle positioning display:
- Live geographic coordinate tracking.
- Interactive or offline schematic map view rendering current vehicle position, heading vector, and track history.
- Prominent badge indicating whether coordinates are **LIVE SATELLITE FIX** or **SIMULATION MODE**.

### Tab 5 — Accelerometer & Road Condition
Road surface vibration analysis:
- Real-time scrolling waveform charts for X, Y, and Z acceleration.
- Road roughness / pothole vibration event detector.
- **Dynamic Threshold Slider**: Allows the driver/operator to adjust the vibration trigger threshold (in g) in real time.
- **Save Threshold Button**: Synchronizes the new threshold immediately to ESP32 / background filter and saves to persistent configuration.

### Tab 6 — Hardware Control
Diagnostic testing suite:
- Manual test toggles for ESP32 Warning LED.
- Manual test pulse for Piezo Buzzer (with safe auto-shutoff timeout).
- Hardware heartbeat and error log viewer.

### Tab 7 — System Settings & Calibration
Configuration manager:
- Laptop IP address and port configuration.
- Camera device index and resolution selector.
- AI detection confidence slider.
- Hardware vs Simulation toggle switch.
- Settings persistence (Save & Apply).
