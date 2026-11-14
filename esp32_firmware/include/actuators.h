#pragma once
/**
 * @file actuators.h
 * @brief Actuator Driver with Non-Blocking Safety Watchdog for LED and Piezo Buzzer.
 */

#include "protocol_defs.h"
#include <Arduino.h>

class ActuatorController {
public:
    ActuatorController(uint8_t led_pin, uint8_t buzzer_pin, uint32_t max_buzzer_ms = 1500);
    void init();
    void update();

    void setLed(bool enable);
    void pulseBuzzer(uint32_t duration_ms = 250);
    void stopBuzzer();

    ActuatorStatus getStatus() const;

private:
    uint8_t _led_pin;
    uint8_t _buzzer_pin;
    uint32_t _max_buzzer_ms;

    bool _led_state;
    bool _buzzer_active;
    uint32_t _buzzer_start_time;
    uint32_t _buzzer_duration;
};
