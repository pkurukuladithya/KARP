#pragma once
/**
 * @file accelerometer_driver.h
 * @brief Configurable I2C Accelerometer Driver (MPU-6050 / ADXL345).
 */

#include "sensor_interface.h"
#include <Wire.h>

class Mpu6050Driver : public IAccelerometerDriver {
public:
    explicit Mpu6050Driver(uint8_t i2c_addr = 0x68, float initial_threshold = 2.20f);
    bool init() override;
    bool read(AccelMeasurement& out) override;
    void setThreshold(float threshold_g) override;
    float getThreshold() const override;
    const char* getModelName() const override { return "MPU-6050"; }

private:
    uint8_t _addr;
    float _threshold_g;
    bool _initialized;
    float _scale_factor; // LSB/g (e.g. 16384 for +/- 2g range)

    bool writeReg(uint8_t reg, uint8_t value);
    bool readRegs(uint8_t reg, uint8_t* buffer, size_t length);
};
