#pragma once
/**
 * @file protocol_defs.h
 * @brief Wire-level JSON protocol types and packet structures for ESP32.
 */

#include <Arduino.h>

struct AccelMeasurement {
    bool valid;
    float ax_g;
    float ay_g;
    float az_g;
    float magnitude_g;
    bool vibration_detected;
};

struct GpsMeasurement {
    bool valid;
    uint8_t fix_quality;
    uint8_t satellites;
    double latitude;
    double longitude;
    float altitude_m;
    float speed_kmh;
    float heading_deg;
};

struct ActuatorStatus {
    bool led_state;
    bool buzzer_active;
};
