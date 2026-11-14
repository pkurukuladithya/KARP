#pragma once
/**
 * @file sensor_interface.h
 * @brief Abstract Base Interface for Accelerometer Sensors.
 */

#include "protocol_defs.h"

class IAccelerometerDriver {
public:
    virtual ~IAccelerometerDriver() = default;
    virtual bool init() = 0;
    virtual bool read(AccelMeasurement& out) = 0;
    virtual void setThreshold(float threshold_g) = 0;
    virtual float getThreshold() const = 0;
    virtual const char* getModelName() const = 0;
};
