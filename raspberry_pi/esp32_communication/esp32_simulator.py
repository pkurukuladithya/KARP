"""
ESP32 Hardware Simulation Worker.
Synthesizes realistic vehicle kinematics, GNSS trajectory, and road surface vibration impacts.
"""

from __future__ import annotations
import math
import random
import time
from typing import Optional
from PySide6.QtCore import QThread, Signal

from shared.protocols.message_schemas import SensorTelemetry, AccelData, GpsData, ActuatorState


class Esp32SimulatorWorker(QThread):
    telemetry_received = Signal(object)  # SensorTelemetry
    connection_changed = Signal(bool)
    log_message = Signal(str)

    def __init__(self, update_hz: float = 20.0, initial_threshold_g: float = 2.20, parent=None):
        super().__init__(parent)
        self.interval = 1.0 / max(1.0, update_hz)
        self.threshold_g = initial_threshold_g
        self._running = True

        # Vehicle Simulation State
        self._t: float = 0.0
        self._seq: int = 0
        self._base_lat: float = 37.7749
        self._base_lon: float = -122.4194
        self._radius: float = 0.003  # ~330 meters track radius
        self._speed_kmh: float = 48.0
        self._led_state: bool = False
        self._buzzer_active: bool = False

    def stop(self) -> None:
        self._running = False
        self.wait(1000)

    def send_threshold(self, threshold_g: float) -> None:
        self.threshold_g = threshold_g
        self.log_message.emit(f"[SIMULATOR] ESP32 threshold updated -> {threshold_g:.2f}g")

    def send_actuator_cmd(self, led: Optional[bool] = None, buzzer_ms: Optional[int] = None) -> None:
        if led is not None:
            self._led_state = led
            self.log_message.emit(f"[SIMULATOR] LED set -> {led}")
        if buzzer_ms is not None:
            self._buzzer_active = True
            self.log_message.emit(f"[SIMULATOR] Buzzer pulse -> {buzzer_ms}ms")

    def run(self) -> None:
        self.connection_changed.emit(True)
        self.log_message.emit("[SIMULATOR] Virtual ESP32 Hardware Initialized (Simulation Mode)")

        while self._running:
            self._t += self.interval
            self._seq += 1

            # 1. Synthesize Closed-Loop Vehicle Navigation Trajectory
            angular_velocity = 0.08  # Radians per sec
            angle = self._t * angular_velocity
            lat = self._base_lat + self._radius * math.sin(angle)
            lon = self._base_lon + self._radius * math.cos(angle)
            heading = (math.degrees(angle) + 90.0) % 360.0
            speed = 45.0 + 5.0 * math.sin(self._t * 0.1) + random.uniform(-0.5, 0.5)

            # 2. Synthesize Triaxial Accelerometer with Road Potholes
            # Baseline: Az ~ 1.0g (gravity), Ax/Ay slight cornering and acceleration
            centripetal_g = (speed / 3.6) ** 2 / (self._radius * 111000.0) / 9.81
            ax = centripetal_g + random.gauss(0.0, 0.03)
            ay = random.gauss(0.0, 0.03)
            az = 1.0 + random.gauss(0.0, 0.04)

            # Periodic Road Bump / Pothole (every ~12 seconds)
            vibe_detected = False
            if int(self._t) % 12 == 0 and (self._t - int(self._t)) < 0.25:
                # Spike acceleration magnitude
                az += 1.6 * math.sin(self._t * 50.0)
                ax += 0.8 * random.uniform(-1, 1)

            mag = math.sqrt(ax * ax + ay * ay + az * az)
            if mag >= self.threshold_g:
                vibe_detected = True

            # 3. Assemble Structured Telemetry Packet
            telemetry = SensorTelemetry(
                seq=self._seq,
                timestamp_ms=int(time.time() * 1000),
                accel=AccelData(
                    valid=True,
                    ax_g=round(ax, 3),
                    ay_g=round(ay, 3),
                    az_g=round(az, 3),
                    magnitude_g=round(mag, 3),
                    vibration_detected=vibe_detected,
                    sensor_model="SIMULATED_MPU6050",
                ),
                gps=GpsData(
                    valid=True,
                    fix_quality=1,
                    satellites=9,
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    altitude_m=18.5,
                    speed_kmh=round(speed, 1),
                    heading_deg=round(heading, 1),
                    is_simulated=True,
                ),
                actuators=ActuatorState(
                    led_warning=self._led_state,
                    buzzer_active=self._buzzer_active,
                ),
            )

            self.telemetry_received.emit(telemetry)
            time.sleep(self.interval)

        self.connection_changed.emit(False)
