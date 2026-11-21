/**
 * @file main.cpp
 * @brief KARP ESP32-S3 Sensor & Actuator Hub Firmware.
 * 
 * Target Board: ESP32-S3 DevKit
 * Sensors:
 *   - MPU6050 Accelerometer (I2C: SDA=GPIO8, SCL=GPIO9, 0x68)
 *   - NEO-6M GPS (UART2: RX=GPIO18, TX=GPIO17, 9600 baud)
 * Actuators:
 *   - RED LED    (GPIO5)  -> Rough road / ADAS Critical Hazard
 *   - YELLOW LED (GPIO6)  -> Moderate road / Blinks while searching for GPS fix
 *   - GREEN LED  (GPIO7)  -> Smooth road / Normal driving
 *   - BUZZER     (GPIO14) -> Audible Collision & Pothole Alert (non-blocking)
 * Host Communication:
 *   - USB Serial at 115200 baud (5 Hz JSON telemetry + bidirectional ADAS commands)
 */

#include <Arduino.h>
#include <Wire.h>
#include <TinyGPSPlus.h>
#include <HardwareSerial.h>
#include <ArduinoJson.h>
#include <math.h>
#include <string.h>

#include "config.h"

// --------------------- HARDWARE OBJECTS ---------------------
HardwareSerial gpsPort(2);
TinyGPSPlus gps;

// --------------------- TIMING & STATE -----------------------
constexpr uint32_t SAMPLE_PERIOD_MS    = 10;    // 100 Hz MPU sampling
constexpr uint32_t OUTPUT_PERIOD_MS    = 200;   // 5 Hz telemetry output
constexpr uint32_t GPS_TIMEOUT_MS      = 3000;  // GPS byte timeout
constexpr uint32_t GPS_FIX_MAX_AGE_MS  = 5000;  // Fix fresh timeout
constexpr uint32_t IMPACT_COOLDOWN_MS  = 2500;  // Pothole reporting cooldown

uint32_t lastSampleMs = 0;
uint32_t lastOutputMs = 0;
uint32_t lastGpsByteMs = 0;
uint32_t lastImpactMs = 0;
bool receivedGpsBytes = false;

// --------------------- MPU6050 DATA -------------------------
float ax = 0.0f, ay = 0.0f, az = 0.0f; // Acceleration in g
float accelerationMagnitude = 1.0f;    // In g
float baselineGravity = 1.0f;         // In g measured during calibration
bool mpuReady = false;

// 250 ms rolling vibration window at 100 Hz
constexpr int WINDOW_SIZE = 25;
float vibrationWindow[WINDOW_SIZE] = {0};
int windowIndex = 0;
bool windowFull = false;
float vibrationRMS = 0.0f;
float vibrationPeak = 0.0f;

// --------------------- VEHICLE & ROAD STATE -----------------
constexpr float MIN_GPS_MOVING_KMH  = 2.0f;
constexpr float STATIONARY_RMS_G    = 0.025f;
constexpr int MOVING_CONFIRM_OUTPUTS = 5;
constexpr int STOP_CONFIRM_OUTPUTS   = 10;
int movingCount = 0;
int stoppedCount = 0;
bool vehicleMoving = false;

// Road Classification Thresholds
constexpr float SMOOTH_RMS_G   = 0.035f;
constexpr float SMOOTH_PEAK_G  = 0.10f;
constexpr float MODERATE_RMS_G = 0.12f;
constexpr float IMPACT_PEAK_G  = 0.35f;

constexpr bool BENCH_LED_TEST_MODE = false;
const char *road = "CALIBRATING";
int confidence = 0;
bool impactWasAboveThreshold = false;

// --------------------- BUZZER & ADAS OVERRIDE ---------------
uint32_t buzzerEndTimeMs = 0;
bool buzzerState = false;

uint32_t adasOverrideEndTimeMs = 0;
String adasAlertLevel = "";

String serialRxBuffer = "";

// Forward Declarations
void setRoadLEDs(bool redOn, bool yellowOn, bool greenOn);
void updateLEDs();
void pulseBuzzer(uint32_t durationMs);
void updateBuzzer();
void serviceGPS();
bool gpsConnected();
bool gpsFixValid();
bool gpsSpeedFresh();
bool initMPU();
bool readAcceleration();
void calibrateMPU();
void updateVibration(float deviationG);
void updateVehicleState();
void classifyRoad();
void outputJSON();
void processIncomingCommand(const String &jsonStr);

// ============================================================================
// ACTUATORS (LEDS & BUZZER)
// ============================================================================
void setRoadLEDs(bool redOn, bool yellowOn, bool greenOn) {
  digitalWrite(RED_LED_PIN, redOn ? HIGH : LOW);
  digitalWrite(YELLOW_LED_PIN, yellowOn ? HIGH : LOW);
  digitalWrite(GREEN_LED_PIN, greenOn ? HIGH : LOW);
}

void testLEDsAtStartup() {
  setRoadLEDs(true, false, false); delay(300);
  setRoadLEDs(false, true, false); delay(300);
  setRoadLEDs(false, false, true); delay(300);
  pulseBuzzer(120);
  delay(150);
  setRoadLEDs(false, false, false);
}

void pulseBuzzer(uint32_t durationMs) {
  uint32_t safeDuration = min(durationMs, (uint32_t)BUZZER_MAX_DURATION_MS);
  buzzerEndTimeMs = millis() + safeDuration;
  digitalWrite(BUZZER_PIN, HIGH);
  buzzerState = true;
}

void updateBuzzer() {
  if (buzzerState && millis() >= buzzerEndTimeMs) {
    digitalWrite(BUZZER_PIN, LOW);
    buzzerState = false;
  }
}

void updateLEDs() {
  uint32_t now = millis();

  // 1. High-Priority ADAS Collision / Departure Alert Override
  if (now < adasOverrideEndTimeMs) {
    if (adasAlertLevel == "CRITICAL") {
      // Rapid flashing Red LED at 10 Hz
      bool blink = (now / 100) % 2 == 0;
      setRoadLEDs(blink, false, false);
      return;
    } else if (adasAlertLevel == "WARNING") {
      // Steady Yellow Caution
      setRoadLEDs(false, true, false);
      return;
    }
  }

  // 2. GPS Searching State: Yellow LED blinks at 2 Hz while searching for fix
  if (!gpsFixValid()) {
    bool searchBlink = (now / 250) % 2 == 0;
    setRoadLEDs(false, searchBlink, false);
    return;
  }

  // 3. Normal Road Condition Classification (with GPS Fix)
  if (strcmp(road, "ROUGH") == 0) {
    setRoadLEDs(true, false, false);
  } else if (strcmp(road, "MODERATE") == 0) {
    setRoadLEDs(false, true, false);
  } else if (strcmp(road, "SMOOTH") == 0) {
    setRoadLEDs(false, false, true);
  } else {
    // CALIBRATING / STATIONARY
    setRoadLEDs(false, false, false);
  }
}

// ============================================================================
// GPS SERVICE & VALIDATION
// ============================================================================
void serviceGPS() {
  while (gpsPort.available()) {
    int byteRead = gpsPort.read();
    if (byteRead >= 0) {
      gps.encode((char)byteRead);
      receivedGpsBytes = true;
      lastGpsByteMs = millis();
    }
  }
}

bool gpsConnected() {
  return receivedGpsBytes && (millis() - lastGpsByteMs < GPS_TIMEOUT_MS);
}

bool gpsFixValid() {
  return gpsConnected() && gps.location.isValid() && (gps.location.age() < GPS_FIX_MAX_AGE_MS);
}

bool gpsSpeedFresh() {
  return gpsFixValid() && gps.speed.isValid() && (gps.speed.age() < GPS_FIX_MAX_AGE_MS);
}

// ============================================================================
// MPU6050 I2C DRIVER
// ============================================================================
bool readMPU(uint8_t reg, uint8_t *data, uint8_t length) {
  Wire.beginTransmission(MPU_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;

  if (Wire.requestFrom((int)MPU_ADDRESS, (int)length) != length) return false;
  for (uint8_t i = 0; i < length; ++i) {
    if (!Wire.available()) return false;
    data[i] = (uint8_t)Wire.read();
  }
  return true;
}

bool writeMPU(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDRESS);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool initMPU() {
  uint8_t whoAmI = 0;
  if (!readMPU(0x75, &whoAmI, 1) || whoAmI != 0x68) {
    return false;
  }
  // Wake up; +/- 2g range; Digital Low Pass Filter (DLPF) enabled; 100 Hz rate divider
  return writeMPU(0x6B, 0x00) &&
         writeMPU(0x1C, 0x00) &&
         writeMPU(0x1A, 0x03) &&
         writeMPU(0x19, 0x09);
}

bool readAcceleration() {
  uint8_t bytes[6];
  if (!readMPU(0x3B, bytes, 6)) return false;

  int16_t rawX = (int16_t)((bytes[0] << 8) | bytes[1]);
  int16_t rawY = (int16_t)((bytes[2] << 8) | bytes[3]);
  int16_t rawZ = (int16_t)((bytes[4] << 8) | bytes[5]);

  ax = rawX / 16384.0f;
  ay = rawY / 16384.0f;
  az = rawZ / 16384.0f;
  accelerationMagnitude = sqrtf(ax * ax + ay * ay + az * az);
  return true;
}

void calibrateMPU() {
  Serial.println("{\"status\":\"CALIBRATING\",\"message\":\"Keep MPU6050 still\"}");
  float total = 0.0f;
  int valid = 0;

  for (int i = 0; i < 200; ++i) {
    serviceGPS();
    if (readAcceleration()) {
      total += accelerationMagnitude;
      ++valid;
    }
    delay(5);
  }

  if (valid < 150) {
    mpuReady = false;
    Serial.println("{\"error\":\"MPU6050_CALIBRATION_FAILED\"}");
    return;
  }
  baselineGravity = total / valid;
  Serial.print("{\"status\":\"CALIBRATION_COMPLETE\",\"baseline\":");
  Serial.print(baselineGravity, 4);
  Serial.println("}");
}

// ============================================================================
// ROAD VIBRATION & STATE ESTIMATION
// ============================================================================
void updateVibration(float deviationG) {
  vibrationWindow[windowIndex++] = deviationG;
  if (windowIndex == WINDOW_SIZE) {
    windowIndex = 0;
    windowFull = true;
  }

  int count = windowFull ? WINDOW_SIZE : windowIndex;
  float squareSum = 0.0f;
  float peak = 0.0f;
  for (int i = 0; i < count; ++i) {
    float val = vibrationWindow[i];
    squareSum += val * val;
    if (val > peak) peak = val;
  }
  vibrationRMS = count ? sqrtf(squareSum / count) : 0.0f;
  vibrationPeak = peak;
}

void updateVehicleState() {
  float speed = gpsSpeedFresh() ? gps.speed.kmph() : 0.0f;
  bool looksMoving = gpsSpeedFresh()
                     ? (speed >= MIN_GPS_MOVING_KMH)
                     : (vibrationRMS >= STATIONARY_RMS_G);

  if (looksMoving) {
    ++movingCount;
    stoppedCount = 0;
    if (movingCount >= MOVING_CONFIRM_OUTPUTS) vehicleMoving = true;
  } else {
    ++stoppedCount;
    movingCount = 0;
    if (stoppedCount >= STOP_CONFIRM_OUTPUTS) vehicleMoving = false;
  }
}

void classifyRoad() {
  if (!mpuReady) {
    road = "SENSOR_ERROR";
    confidence = 0;
  } else if (!windowFull) {
    road = "CALIBRATING";
    confidence = 0;
  } else if (!vehicleMoving && !BENCH_LED_TEST_MODE) {
    road = "STATIONARY";
    confidence = 0;
  } else if (vibrationRMS < SMOOTH_RMS_G && vibrationPeak < SMOOTH_PEAK_G) {
    road = "SMOOTH";
    confidence = 90;
  } else if (vibrationRMS < MODERATE_RMS_G && vibrationPeak < IMPACT_PEAK_G) {
    road = "MODERATE";
    confidence = 70;
  } else {
    road = "ROUGH";
    confidence = 65;
  }
}

// ============================================================================
// TELEMETRY BROADCAST (JSON AT 5 HZ)
// ============================================================================
void outputJSON() {
  bool gpsOk = gpsFixValid();
  bool speedOk = gpsSpeedFresh();
  updateVehicleState();
  classifyRoad();
  updateLEDs();

  // Pothole / Impact Candidate Detection
  bool aboveImpact = mpuReady && windowFull && vehicleMoving && (vibrationPeak >= IMPACT_PEAK_G);
  bool impactCandidate = false;
  if (aboveImpact && !impactWasAboveThreshold &&
      (lastImpactMs == 0 || millis() - lastImpactMs >= IMPACT_COOLDOWN_MS)) {
    impactCandidate = true;
    lastImpactMs = millis();
    pulseBuzzer(120); // Brief warning chirp on pothole candidate
  }
  impactWasAboveThreshold = aboveImpact;

  // Build JSON Document
  JsonDocument doc;
  doc["type"] = "sensor_telemetry";
  doc["timestamp_ms"] = millis();

  // GPS Data
  doc["gpsConnected"] = gpsConnected();
  doc["gpsValid"] = gpsOk;
  if (gpsOk) {
    doc["lat"] = serialized(String(gps.location.lat(), 6));
    doc["lon"] = serialized(String(gps.location.lng(), 6));
    doc["altitude_m"] = round(gps.altitude.meters() * 10.0f) / 10.0f;
    doc["heading_deg"] = round(gps.course.deg() * 10.0f) / 10.0f;
  } else {
    doc["lat"] = nullptr;
    doc["lon"] = nullptr;
    doc["altitude_m"] = 0.0;
    doc["heading_deg"] = 0.0;
  }
  doc["speed"] = (vehicleMoving && speedOk) ? (round(gps.speed.kmph() * 10.0f) / 10.0f) : 0.0;
  doc["rawSpeed"] = speedOk ? (round(gps.speed.kmph() * 10.0f) / 10.0f) : 0.0;
  doc["satellites"] = (gpsConnected() && gps.satellites.isValid()) ? gps.satellites.value() : 0;

  // MPU6050 Acceleration Data
  doc["mpuConnected"] = mpuReady;
  doc["ax"] = round(ax * 1000.0f) / 1000.0f;
  doc["ay"] = round(ay * 1000.0f) / 1000.0f;
  doc["az"] = round(az * 1000.0f) / 1000.0f;
  doc["acceleration"] = round(accelerationMagnitude * 1000.0f) / 1000.0f;
  doc["baseline"] = round(baselineGravity * 1000.0f) / 1000.0f;
  doc["vibration"] = round(vibrationRMS * 1000.0f) / 1000.0f;
  doc["vibrationPeak"] = round(vibrationPeak * 1000.0f) / 1000.0f;
  doc["road"] = road;
  doc["confidence"] = confidence;
  doc["potholeCandidate"] = impactCandidate;
  doc["vehicleMoving"] = vehicleMoving;
  doc["vehicleState"] = vehicleMoving ? "MOVING" : "STATIONARY";

  // Actuator State
  JsonObject act = doc["actuators"].to<JsonObject>();
  act["buzzer"] = buzzerState;
  act["led"] = (road != nullptr) ? road : "OFF";

  // Stream single-line JSON to Host
  serializeJson(doc, Serial);
  Serial.println();
}

// ============================================================================
// INCOMING COMMAND PROCESSING FROM PI
// ============================================================================
void processIncomingCommand(const String &jsonStr) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, jsonStr);
  if (err) return;

  const char *cmd = doc["cmd"] | doc["type"];
  if (!cmd) return;

  if (strcmp(cmd, "actuate") == 0 || strcmp(cmd, "cmd_actuator") == 0) {
    uint32_t bzMs = doc["buzzer_ms"] | doc["buzzer_duration_ms"] | 0;
    if (bzMs > 0) {
      pulseBuzzer(bzMs);
    }
    const char *lvl = doc["level"] | doc["led"];
    if (lvl) {
      adasAlertLevel = String(lvl);
      adasOverrideEndTimeMs = millis() + (bzMs > 0 ? bzMs + 200 : 500);
    }
  }
}

// ============================================================================
// MAIN SETUP & LOOP
// ============================================================================
void setup() {
  Serial.begin(HOST_SERIAL_BAUD);
  serialRxBuffer.reserve(256);
  delay(1500); // Wait for USB CDC enumeration on ESP32-S3

  Serial.println("{\"boot\":\"ESP32_S3_STARTING\"}");

  // Setup GPIO Actuators
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(YELLOW_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  setRoadLEDs(false, false, false);

  // Self-test LEDs & Buzzer
  testLEDsAtStartup();

  // Setup GPS UART2
  pinMode(GPS_PPS_PIN, INPUT);
  gpsPort.begin(GPS_BAUD_RATE, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  // Setup I2C MPU6050
  pinMode(MPU_INT_PIN, INPUT);
  Wire.begin(MPU_SDA_PIN, MPU_SCL_PIN);
  Wire.setClock(I2C_CLOCK_SPEED);
  Wire.setTimeOut(50);

  mpuReady = initMPU();
  if (mpuReady) {
    calibrateMPU();
  } else {
    Serial.println("{\"error\":\"MPU6050_NOT_FOUND\"}");
  }

  lastSampleMs = millis();
  lastOutputMs = millis();
}

void loop() {
  serviceGPS();
  updateBuzzer();
  updateLEDs();
  uint32_t now = millis();

  // 1. MPU Sampling at 100 Hz
  if (now - lastSampleMs >= SAMPLE_PERIOD_MS) {
    lastSampleMs = now;
    if (mpuReady) {
      if (readAcceleration()) {
        float dev = fabsf(accelerationMagnitude - baselineGravity);
        updateVibration(dev);
      } else {
        mpuReady = false;
        Serial.println("{\"error\":\"MPU_READ_FAILED\"}");
      }
    }
  }

  // 2. Telemetry Output at 5 Hz
  if (now - lastOutputMs >= OUTPUT_PERIOD_MS) {
    lastOutputMs = now;
    outputJSON();
  }

  // 3. Receive Command from Pi
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      serialRxBuffer.trim();
      if (serialRxBuffer.length() > 0) {
        processIncomingCommand(serialRxBuffer);
      }
      serialRxBuffer = "";
    } else if (c != '\r') {
      serialRxBuffer += c;
      if (serialRxBuffer.length() > 512) serialRxBuffer = "";
    }
  }
}
