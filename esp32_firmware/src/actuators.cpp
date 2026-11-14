#include "actuators.h"

ActuatorController::ActuatorController(uint8_t led_pin, uint8_t buzzer_pin, uint32_t max_buzzer_ms)
    : _led_pin(led_pin),
      _buzzer_pin(buzzer_pin),
      _max_buzzer_ms(max_buzzer_ms),
      _led_state(false),
      _buzzer_active(false),
      _buzzer_start_time(0),
      _buzzer_duration(0) {}

void ActuatorController::init() {
    pinMode(_led_pin, OUTPUT);
    pinMode(_buzzer_pin, OUTPUT);
    digitalWrite(_led_pin, LOW);
    digitalWrite(_buzzer_pin, LOW);
}

void ActuatorController::setLed(bool enable) {
    _led_state = enable;
    digitalWrite(_led_pin, _led_state ? HIGH : LOW);
}

void ActuatorController::pulseBuzzer(uint32_t duration_ms) {
    // Safety clamp: do not exceed maximum duration
    uint32_t safe_duration = (duration_ms > _max_buzzer_ms) ? _max_buzzer_ms : duration_ms;
    _buzzer_duration = safe_duration;
    _buzzer_start_time = millis();
    _buzzer_active = true;
    digitalWrite(_buzzer_pin, HIGH);
}

void ActuatorController::stopBuzzer() {
    _buzzer_active = false;
    digitalWrite(_buzzer_pin, LOW);
}

void ActuatorController::update() {
    if (_buzzer_active) {
        uint32_t elapsed = millis() - _buzzer_start_time;
        // Hardware Watchdog check
        if (elapsed >= _buzzer_duration || elapsed >= _max_buzzer_ms) {
            stopBuzzer();
        }
    }
}

ActuatorStatus ActuatorController::getStatus() const {
    ActuatorStatus status;
    status.led_state = _led_state;
    status.buzzer_active = _buzzer_active;
    return status;
}
