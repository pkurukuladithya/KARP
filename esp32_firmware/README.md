# KARP ESP32 Embedded Sensor & Actuator Firmware

## 1. Overview
The **KARP ESP32 Firmware** is an embedded real-time sensor node that connects to the Raspberry Pi 4B over USB-CDC Serial at **115200 baud**. It samples:
- **I2C Triaxial Accelerometer** (Ax, Ay, Az, Magnitude, and local vibration spike detection) at 20-50 Hz.
- **UART GPS** (NMEA GGA/RMC sentences: latitude, longitude, altitude, ground speed, heading, satellite count, fix quality).
- **Actuators**: External hazard warning LED (GPIO 2) and active audible piezo buzzer (GPIO 4) with **Hardware Watchdog** auto-shutoff timeout (max 1.5s).

---

## 2. Configuration & Modular Hardware Interfacing

All pins, I2C addresses, and baud rates are centralized in [`include/config.h`](file:///esp32_firmware/include/config.h):

```c
// Accelerometer (I2C)
#define I2C_SDA_PIN             21
#define I2C_SCL_PIN             22
#define MPU6050_I2C_ADDR_PRIMARY 0x68

// GPS (Hardware Serial 2)
#define GPS_RX_PIN              16  // Connect to GPS TX
#define GPS_TX_PIN              17  // Connect to GPS RX
#define GPS_BAUD_RATE           9600

// Actuators
#define PIN_WARNING_LED         2
#define PIN_PIEZO_BUZZER        4
#define BUZZER_MAX_DURATION_MS  1500
```

---

## 3. Build & Flash via PlatformIO

### Step 1: Install PlatformIO Core
```bash
pip install platformio
```

### Step 2: Compile Firmware
```bash
cd esp32_firmware
pio run
```

### Step 3: Flash to ESP32
Connect the ESP32 to your workstation or Raspberry Pi via USB:
```bash
pio run --target upload
```

### Step 4: Serial Monitor
```bash
pio device monitor --baud 115200
```

You will observe structured line-delimited JSON packets matching the KARP telemetry schema:
```json
{"type":"sensor_telemetry","seq":42,"timestamp_ms":2105,"accel":{"valid":true,"ax_g":0.02,"ay_g":-0.01,"az_g":1.01,"magnitude_g":1.01,"vibration_detected":false},"gps":{"valid":false,"fix_quality":0,"satellites":0,"latitude":0.0,"longitude":0.0,"altitude_m":0.0,"speed_kmh":0.0,"heading_deg":0.0},"actuators":{"led_warning":false,"buzzer_active":false}}
```
