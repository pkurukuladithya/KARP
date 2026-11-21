#pragma once
/**
 * @file config.h
 * @brief Centralized Hardware Configuration for KARP ESP32-S3 Firmware.
 * 
 * Hardware Pinout (ESP32-S3 DevKit):
 *   - MPU6050 Accelerometer: SDA -> GPIO 8, SCL -> GPIO 9, INT -> GPIO 12 (0x68)
 *   - NEO-6M GPS: RX -> GPIO 18 (from GPS TXD), TX -> GPIO 17 (to GPS RXD), PPS -> GPIO 4
 *   - Status LEDs:
 *       RED LED    -> GPIO 5 (ROUGH / Critical ADAS Hazard)
 *       YELLOW LED -> GPIO 6 (MODERATE / GPS Searching Blink)
 *       GREEN LED  -> GPIO 7 (SMOOTH / Normal Operation)
 *   - Piezo Buzzer -> GPIO 14 (Audible Warning Buzzer)
 */

#include <Arduino.h>

// ============================================================================
// 1. SERIAL COMMUNICATION (USB CDC TO RASPBERRY PI)
// ============================================================================
#define HOST_SERIAL_BAUD        115200
#define TELEMETRY_RATE_HZ       5           // Telemetry broadcast frequency (5 Hz / 200 ms)
#define TELEMETRY_INTERVAL_MS   (1000 / TELEMETRY_RATE_HZ)

// ============================================================================
// 2. I2C MPU6050 ACCELEROMETER CONFIGURATION
// ============================================================================
constexpr uint8_t MPU_SDA_PIN   = 8;
constexpr uint8_t MPU_SCL_PIN   = 9;
constexpr uint8_t MPU_INT_PIN   = 12;
constexpr uint8_t MPU_ADDRESS   = 0x68;

#define I2C_CLOCK_SPEED         100000      // 100 kHz Standard I2C

// ============================================================================
// 3. UART GPS CONFIGURATION (NEO-6M)
// ============================================================================
constexpr uint8_t GPS_RX_PIN    = 18;       // ESP32 RX receives from GPS TXD
constexpr uint8_t GPS_TX_PIN    = 17;       // ESP32 TX sends to GPS RXD
constexpr uint8_t GPS_PPS_PIN   = 4;        // Optional PPS pin
#define GPS_BAUD_RATE           9600        // Standard NEO-6M baud rate

// ============================================================================
// 4. LED & BUZZER ACTUATOR CONFIGURATION
// ============================================================================
constexpr uint8_t RED_LED_PIN    = 5;       // GPIO 5 -> 330 ohm -> Red Anode
constexpr uint8_t YELLOW_LED_PIN = 6;       // GPIO 6 -> 330 ohm -> Yellow Anode
constexpr uint8_t GREEN_LED_PIN  = 7;       // GPIO 7 -> 330 ohm -> Green Anode
constexpr uint8_t BUZZER_PIN     = 14;      // GPIO 14 -> Buzzer

// Safety Watchdog
#define BUZZER_MAX_DURATION_MS  2000        // Safety maximum continuous buzz (2 sec)
#define BUZZER_DEFAULT_PULSE_MS 250         // Standard ADAS pulse duration
