/**
 * @file main.cpp
 * @brief KARP ESP32 Sensor & Hardware Controller Main Application.
 * 
 * Reads I2C triaxial accelerometer and UART GPS, executes non-blocking JSON command framing,
 * broadcasts telemetry at 20 Hz, and controls warning LEDs and Piezo Buzzers with watchdog safety.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Wire.h>

#include "config.h"
#include "protocol_defs.h"
#include "accelerometer_driver.h"
#include "gps_parser.h"
#include "actuators.h"

// Hardware Drivers
Mpu6050Driver accel(MPU6050_I2C_ADDR_PRIMARY, DEFAULT_VIBRATION_THRESHOLD_G);
GpsParser gps;
ActuatorController actuators(PIN_WARNING_LED, PIN_PIEZO_BUZZER, BUZZER_MAX_DURATION_MS);

// State Variables
uint32_t last_telemetry_time = 0;
uint32_t sequence_id = 0;
String serial_rx_buffer = "";

void processIncomingCommand(const String& json_str);
void broadcastTelemetry();

void setup() {
    // 1. Initialize Host USB Serial (Raspberry Pi Communication)
    Serial.begin(HOST_SERIAL_BAUD);
    serial_rx_buffer.reserve(256);

    // 2. Initialize Actuators & Safety Watchdog
    actuators.init();

    // 3. Initialize I2C Bus for Accelerometer
    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, I2C_CLOCK_SPEED);
    bool accel_ok = accel.init();

    // 4. Initialize Hardware UART for GPS (Serial 2)
    bool gps_ok = gps.init(Serial2, GPS_RX_PIN, GPS_TX_PIN, GPS_BAUD_RATE);

    // Boot notification
    JsonDocument boot_doc;
    boot_doc["type"] = "boot_status";
    boot_doc["accel_ok"] = accel_ok;
    boot_doc["gps_ok"] = gps_ok;
    boot_doc["sensor_model"] = accel.getModelName();
    boot_doc["default_threshold_g"] = accel.getThreshold();
    serializeJson(boot_doc, Serial);
    Serial.println();
}

void loop() {
    // 1. Maintain background tasks
    gps.update();
    actuators.update();

    // 2. Read incoming command line from Raspberry Pi (non-blocking)
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n') {
            serial_rx_buffer.trim();
            if (serial_rx_buffer.length() > 0) {
                processIncomingCommand(serial_rx_buffer);
            }
            serial_rx_buffer = "";
        } else if (c != '\r') {
            serial_rx_buffer += c;
            // Prevent buffer overflow
            if (serial_rx_buffer.length() > 512) {
                serial_rx_buffer = "";
            }
        }
    }

    // 3. Periodic Telemetry Broadcast (20 Hz)
    uint32_t now = millis();
    if (now - last_telemetry_time >= TELEMETRY_INTERVAL_MS) {
        last_telemetry_time = now;
        broadcastTelemetry();
    }
}

void broadcastTelemetry() {
    sequence_id++;

    // Fetch Accelerometer Measurements
    AccelMeasurement accel_data;
    accel.read(accel_data);

    // Fetch GPS Measurements
    GpsMeasurement gps_data;
    gps.getMeasurement(gps_data);

    // Fetch Actuator Status
    ActuatorStatus act_status = actuators.getStatus();

    // Build JSON Document
    JsonDocument doc;
    doc["type"] = "sensor_telemetry";
    doc["seq"] = sequence_id;
    doc["timestamp_ms"] = millis();

    // Accel object
    JsonObject accel_obj = doc["accel"].to<JsonObject>();
    accel_obj["valid"] = accel_data.valid;
    accel_obj["ax_g"] = round(accel_data.ax_g * 1000.0f) / 1000.0f;
    accel_obj["ay_g"] = round(accel_data.ay_g * 1000.0f) / 1000.0f;
    accel_obj["az_g"] = round(accel_data.az_g * 1000.0f) / 1000.0f;
    accel_obj["magnitude_g"] = round(accel_data.magnitude_g * 1000.0f) / 1000.0f;
    accel_obj["vibration_detected"] = accel_data.vibration_detected;

    // GPS object
    JsonObject gps_obj = doc["gps"].to<JsonObject>();
    gps_obj["valid"] = gps_data.valid;
    gps_obj["fix_quality"] = gps_data.fix_quality;
    gps_obj["satellites"] = gps_data.satellites;
    gps_obj["latitude"] = gps_data.latitude;
    gps_obj["longitude"] = gps_data.longitude;
    gps_obj["altitude_m"] = round(gps_data.altitude_m * 10.0f) / 10.0f;
    gps_obj["speed_kmh"] = round(gps_data.speed_kmh * 10.0f) / 10.0f;
    gps_obj["heading_deg"] = round(gps_data.heading_deg * 10.0f) / 10.0f;

    // Actuators object
    JsonObject act_obj = doc["actuators"].to<JsonObject>();
    act_obj["led_warning"] = act_status.led_state;
    act_obj["buzzer_active"] = act_status.buzzer_active;

    // Stream single-line JSON terminated with \n
    serializeJson(doc, Serial);
    Serial.println();
}

void processIncomingCommand(const String& json_str) {
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, json_str);
    if (error) {
        return;
    }

    const char* cmd_type = doc["type"];
    if (!cmd_type) return;

    if (strcmp(cmd_type, "cmd_set_vibration_threshold") == 0) {
        float new_thresh = doc["threshold_g"] | accel.getThreshold();
        accel.setThreshold(new_thresh);

        // Send ACK
        JsonDocument ack_doc;
        ack_doc["type"] = "ack";
        ack_doc["cmd"] = "cmd_set_vibration_threshold";
        ack_doc["status"] = "applied";
        ack_doc["active_threshold_g"] = accel.getThreshold();
        serializeJson(ack_doc, Serial);
        Serial.println();
    } 
    else if (strcmp(cmd_type, "cmd_actuator") == 0) {
        if (doc["led"].is<bool>()) {
            actuators.setLed(doc["led"].as<bool>());
        }
        if (doc["buzzer_duration_ms"].is<uint32_t>()) {
            actuators.pulseBuzzer(doc["buzzer_duration_ms"].as<uint32_t>());
        }

        JsonDocument ack_doc;
        ack_doc["type"] = "ack";
        ack_doc["cmd"] = "cmd_actuator";
        ack_doc["status"] = "applied";
        serializeJson(ack_doc, Serial);
        Serial.println();
    }
}
