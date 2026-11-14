#pragma once
/**
 * @file config.h
 * @brief Centralized Hardware Configuration for KARP ESP32 Firmware.
 * 
 * IMPORTANT HARDWARE INTEGRATION NOTES:
 * - Accelerometer Model: Configurable below (Default: MPU-6050 at 0x68). 
 *   If using ADXL345, set ACCEL_TYPE_ADXL345 and adjust I2C address to 0x53.
 * - GPS Module: Standard NMEA UART GPS (NEO-6M / NEO-8M) on UART2 (GPIO 16/17).
 * - All pin definitions and communication rates can be modified in this file.
 */

#include <Arduino.h>

// ============================================================================
// 1. SERIAL COMMUNICATION (USB-CDC TO RASPBERRY PI)
// ============================================================================
#define HOST_SERIAL_BAUD        115200
#define TELEMETRY_RATE_HZ       20          // Telemetry broadcast frequency (20 Hz)
#define TELEMETRY_INTERVAL_MS   (1000 / TELEMETRY_RATE_HZ)

// ============================================================================
// 2. I2C ACCELEROMETER CONFIGURATION
// ============================================================================
#define I2C_SDA_PIN             21          // ESP32 Hardware I2C SDA
#define I2C_SCL_PIN             22          // ESP32 Hardware I2C SCL
#define I2C_CLOCK_SPEED         400000      // 400 kHz Fast-Mode I2C

// Select Sensor Driver (Uncomment desired driver):
#define ACCEL_DRIVER_MPU6050    1
// #define ACCEL_DRIVER_ADXL345 1

#define MPU6050_I2C_ADDR_PRIMARY   0x68     // AD0 pulled to GND
#define MPU6050_I2C_ADDR_SECONDARY 0x69     // AD0 pulled to VCC
#define ADXL345_I2C_ADDR           0x53     // SDO pulled to GND

#define DEFAULT_VIBRATION_THRESHOLD_G  2.20f // Initial vibration trigger threshold in g

// ============================================================================
// 3. UART GPS CONFIGURATION
// ============================================================================
#define GPS_UART_NUM            2           // Hardware Serial 2
#define GPS_RX_PIN              16          // Connected to GPS TX pin
#define GPS_TX_PIN              17          // Connected to GPS RX pin
#define GPS_BAUD_RATE           9600        // Standard NMEA baud rate

// ============================================================================
// 4. ACTUATOR & SAFETY SAFEGUARDS
// ============================================================================
#define PIN_WARNING_LED         2           // Status / Hazard Warning LED (Onboard or external)
#define PIN_PIEZO_BUZZER        4           // Audible Warning Piezo Buzzer

// Safety Watchdog: Prevents buzzer from staying ON continuously in case of crash or command lock
#define BUZZER_MAX_DURATION_MS  1500        // Absolute maximum continuous buzzer time (1.5 seconds)
#define BUZZER_DEFAULT_PULSE_MS 250         // Standard warning pulse duration
