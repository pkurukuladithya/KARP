# KARP Hardware Connections & Interfacing Guide

This document specifies the electrical wiring, pin assignments, and communication buses connecting the ESP32, Raspberry Pi 4B, sensors, and display.

---

## 1. Hardware Status Summary

| Subsystem | Hardware Component | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Main AI Unit** | Laptop (RTX 4050, 16GB RAM) | Confirmed | Connects over Wi-Fi 5GHz / Ethernet |
| **Edge Controller** | Raspberry Pi 4B (4GB RAM) | Confirmed | RPi OS 64-bit Desktop, USB camera, HDMI |
| **Display** | Mini HDMI Display (1024x600 / 1280x720) | Confirmed | Connected to Micro-HDMI 0 on RPi 4 |
| **Camera** | USB Front-Facing UVC Web Camera | Confirmed | 720p / 1080p, connected to USB 3.0 port |
| **Microcontroller** | ESP32-WROOM-32 DevKit | Confirmed | Connected to RPi USB via Micro-USB cable |
| **Accelerometer** | Triaxial I2C (MPU-6050 / ADXL345) | **Model Configurable** | Default I2C: SDA=GPIO21, SCL=GPIO22 |
| **GPS Module** | UART NMEA (NEO-6M / NEO-8M) | **Model Configurable** | Default UART2: RX2=GPIO16, TX2=GPIO17 |
| **Actuators** | Warning LED & Active Piezo Buzzer | **Pins Configurable** | Default: LED=GPIO2, Buzzer=GPIO4 |

> [!IMPORTANT]
> The exact accelerometer chip (MPU-6050, MPU-9250, ADXL345, or LSM6DS3) and exact GPS module baud rate are abstracted behind the modular firmware driver layer in `esp32_firmware/include/config.h`. Any pin or I2C address can be changed in that single header without modifying core logic.

---

## 2. ESP32 Pinout & Wiring Diagram

### 2.1 Accelerometer (I2C Bus)
- **VCC**: 3.3V (Pin 3V3 on ESP32)
- **GND**: Ground (Pin GND on ESP32)
- **SDA**: ESP32 GPIO 21 (External 4.7kΩ pull-up to 3.3V recommended if breakout board lacks pull-ups)
- **SCL**: ESP32 GPIO 22 (External 4.7kΩ pull-up to 3.3V recommended)
- **Default I2C Addresses**:
  - `0x68` (MPU-6050 with AD0 tied to GND)
  - `0x69` (MPU-6050 with AD0 tied to 3.3V)
  - `0x53` (ADXL345 with SDO tied to GND)

### 2.2 GPS Module (UART2)
- **VCC**: 3.3V or 5V (Check GPS breakout regulator; NEO-6M typically takes 5V with 3.3V UART)
- **GND**: ESP32 GND
- **TX (GPS)**: Connect to ESP32 **GPIO 16 (RX2)**
- **RX (GPS)**: Connect to ESP32 **GPIO 17 (TX2)** (Optional if GPS only transmits)
- **Baud Rate**: 9600 bps standard (configurable to 115200)

### 2.3 Actuators (Warning LED & Piezo Buzzer)
- **Status / Warning LED**: Anode to ESP32 **GPIO 2** via 330Ω current-limiting resistor, Cathode to GND.
- **Audible Piezo Buzzer**:
  - Positive terminal to ESP32 **GPIO 4** (or through an NPN transistor 2N2222 if driving >15mA buzzer)
  - Negative terminal to GND.
  - *Firmware safety feature*: The firmware watchdog forces GPIO 4 low after 1500 ms maximum continuous pulse to protect auditory comfort and buzzer coil lifespan.

---

## 3. Raspberry Pi 4 Connections

1. **Power Supply**: Official Raspberry Pi 5.1V / 3.0A USB-C power supply. Do not power from laptop USB ports.
2. **HDMI Display**: Connect Mini HDMI display to **Micro-HDMI Port 0** (closest to the USB-C power input).
3. **USB Camera**: Connect front road camera to **USB 3.0 Port** (blue port) for highest transfer bandwidth.
4. **ESP32 Connection**: Connect standard USB-A to Micro-USB cable from Pi USB 2.0 port to ESP32. Linux automatically mounts as `/dev/ttyUSB0` or `/dev/ttyACM0`.

---

## 4. Local Area Network Configuration

To achieve reliable 30 FPS video streaming between Pi and Laptop:
1. Connect both Laptop and Pi to the same 5 GHz Wi-Fi access point or a dedicated Ethernet switch/crossover cable.
2. Assign static IP addresses (e.g. Laptop `192.168.1.100`, Pi `192.168.1.101`).
3. Ensure ports `5000` (UDP/TCP video), `5001` (UDP/TCP video), and `8765` (WebSocket) are open on the laptop firewall.
