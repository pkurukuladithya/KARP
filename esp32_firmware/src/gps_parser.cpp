#include "gps_parser.h"

GpsParser::GpsParser() : _serial(nullptr), _initialized(false), _last_fix_time(0) {}

bool GpsParser::init(HardwareSerial& serial_port, int rx_pin, int tx_pin, uint32_t baud) {
    _serial = &serial_port;
    _serial->begin(baud, SERIAL_8N1, rx_pin, tx_pin);
    _initialized = true;
    return true;
}

void GpsParser::update() {
    if (!_initialized || !_serial) return;

    while (_serial->available() > 0) {
        char c = (char)_serial->read();
        _gps.encode(c);
    }
}

bool GpsParser::getMeasurement(GpsMeasurement& out) {
    if (!_initialized) {
        out.valid = false;
        return false;
    }

    out.satellites = _gps.satellites.isValid() ? (uint8_t)_gps.satellites.value() : 0;

    // Check if location is valid and updated within the last 5 seconds
    if (_gps.location.isValid() && _gps.location.age() < 5000) {
        out.valid = true;
        out.fix_quality = 1;
        out.latitude = _gps.location.lat();
        out.longitude = _gps.location.lng();
        out.altitude_m = _gps.altitude.isValid() ? (float)_gps.altitude.meters() : 0.0f;
        out.speed_kmh = _gps.speed.isValid() ? (float)_gps.speed.kmph() : 0.0f;
        out.heading_deg = _gps.course.isValid() ? (float)_gps.course.deg() : 0.0f;
        return true;
    } else {
        out.valid = false;
        out.fix_quality = 0;
        out.latitude = 0.0;
        out.longitude = 0.0;
        out.altitude_m = 0.0f;
        out.speed_kmh = 0.0f;
        out.heading_deg = 0.0f;
        return false;
    }
}
