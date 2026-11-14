#pragma once
/**
 * @file gps_parser.h
 * @brief NMEA GPS Serial Parser using Hardware UART.
 */

#include "protocol_defs.h"
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>

class GpsParser {
public:
    GpsParser();
    bool init(HardwareSerial& serial_port, int rx_pin, int tx_pin, uint32_t baud);
    void update();
    bool getMeasurement(GpsMeasurement& out);

private:
    HardwareSerial* _serial;
    TinyGPSPlus _gps;
    bool _initialized;
    uint32_t _last_fix_time;
};
