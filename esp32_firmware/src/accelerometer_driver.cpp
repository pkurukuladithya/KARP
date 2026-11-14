#include "accelerometer_driver.h"
#include <math.h>

#define MPU6050_REG_PWR_MGMT_1   0x6B
#define MPU6050_REG_ACCEL_CONFIG 0x1C
#define MPU6050_REG_ACCEL_XOUT_H 0x3B
#define MPU6050_REG_WHO_AM_I     0x75

Mpu6050Driver::Mpu6050Driver(uint8_t i2c_addr, float initial_threshold)
    : _addr(i2c_addr), _threshold_g(initial_threshold), _initialized(false), _scale_factor(16384.0f) {}

bool Mpu6050Driver::init() {
    Wire.beginTransmission(_addr);
    if (Wire.endTransmission() != 0) {
        _initialized = false;
        return false;
    }

    // Check WHO_AM_I register (Expected 0x68)
    uint8_t whoami = 0;
    if (!readRegs(MPU6050_REG_WHO_AM_I, &whoami, 1) || (whoami != 0x68 && whoami != 0x70 && whoami != 0x72)) {
        // Device not responding properly
        _initialized = false;
        return false;
    }

    // Wake up MPU6050 (Clear sleep bit in PWR_MGMT_1)
    if (!writeReg(MPU6050_REG_PWR_MGMT_1, 0x00)) {
        _initialized = false;
        return false;
    }

    // Set Full-Scale Accelerometer Range to +/- 4g (0x08 -> 8192 LSB/g) for road dynamic headroom
    if (!writeReg(MPU6050_REG_ACCEL_CONFIG, 0x08)) {
        _initialized = false;
        return false;
    }
    _scale_factor = 8192.0f;

    _initialized = true;
    return true;
}

bool Mpu6050Driver::writeReg(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(_addr);
    Wire.write(reg);
    Wire.write(value);
    return (Wire.endTransmission() == 0);
}

bool Mpu6050Driver::readRegs(uint8_t reg, uint8_t* buffer, size_t length) {
    Wire.beginTransmission(_addr);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) {
        return false;
    }
    size_t count = Wire.requestFrom(_addr, (uint8_t)length);
    if (count != length) {
        return false;
    }
    for (size_t i = 0; i < length; i++) {
        buffer[i] = Wire.read();
    }
    return true;
}

bool Mpu6050Driver::read(AccelMeasurement& out) {
    if (!_initialized) {
        out.valid = false;
        return false;
    }

    uint8_t raw_data[6];
    if (!readRegs(MPU6050_REG_ACCEL_XOUT_H, raw_data, 6)) {
        out.valid = false;
        return false;
    }

    int16_t raw_ax = (int16_t)((raw_data[0] << 8) | raw_data[1]);
    int16_t raw_ay = (int16_t)((raw_data[2] << 8) | raw_data[3]);
    int16_t raw_az = (int16_t)((raw_data[4] << 8) | raw_data[5]);

    out.ax_g = (float)raw_ax / _scale_factor;
    out.ay_g = (float)raw_ay / _scale_factor;
    out.az_g = (float)raw_az / _scale_factor;

    out.magnitude_g = sqrtf(out.ax_g * out.ax_g + out.ay_g * out.ay_g + out.az_g * out.az_g);
    out.vibration_detected = (out.magnitude_g >= _threshold_g);
    out.valid = true;

    return true;
}

void Mpu6050Driver::setThreshold(float threshold_g) {
    if (threshold_g >= 0.5f && threshold_g <= 10.0f) {
        _threshold_g = threshold_g;
    }
}

float Mpu6050Driver::getThreshold() const {
    return _threshold_g;
}
