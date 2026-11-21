"""Only real sensor values may reach the UI: no fake speed / position without ESP32 + GPS fix."""

from brain.esp32 import empty_snapshot
from brain.vehicle_state import (
    GPS_CONNECTING,
    GPS_ESP_OFFLINE,
    GPS_FIX,
    GPS_NO_DATA,
    VehicleStateEstimator,
)


def online(**kw):
    t = dict(empty_snapshot(), connected=True, link="ONLINE", mpu_connected=True, road="SMOOTH",
             gps_connected=True, satellites=0)
    t.update(kw)
    return t


def fix(raw=42.0, moving=True, vib=0.08, heading=90.0, **kw):
    return online(gps_valid=True, lat=6.9271, lon=79.8612, satellites=8, raw_speed_kmh=raw,
                  speed_kmh=raw if moving else 0.0, vehicle_moving=moving, vibration=vib,
                  heading_deg=heading, **kw)


def test_esp32_offline_shows_nothing():
    vs = VehicleStateEstimator().update(empty_snapshot())
    assert vs.gps == GPS_ESP_OFFLINE and not vs.esp_online
    assert vs.speed_kmh is None and vs.speed_text == "--" and vs.speed_status == "NO ESP32"
    assert vs.lat is None and vs.road is None and vs.road_text == "ESP32 OFF"
    assert vs.gps_text == "ESP32 NOT CONNECTED"


def test_stale_esp_values_are_not_used():
    t = fix()
    t["connected"] = False  # last packet had a fix, but the link is gone
    vs = VehicleStateEstimator().update(t)
    assert vs.gps == GPS_ESP_OFFLINE and vs.speed_kmh is None


def test_gps_connecting_never_shows_speed():
    # Firmware sends speed 0 without a fix, and a raw value could still be non-zero: neither may be shown
    vs = VehicleStateEstimator().update(online(satellites=3, speed_kmh=12.0, raw_speed_kmh=12.0))
    assert vs.gps == GPS_CONNECTING and vs.speed_kmh is None and vs.speed_text == "--"
    assert vs.speed_status == "GPS CONNECTING" and vs.gps_text == "GPS CONNECTING... (3 SATS)"
    assert vs.lat is None and vs.heading_deg is None
    assert vs.road_text == "SMOOTH"  # MPU data is real even without GPS


def test_gps_module_silent():
    vs = VehicleStateEstimator().update(online(gps_connected=False))
    assert vs.gps == GPS_NO_DATA and vs.speed_kmh is None and vs.gps_text == "GPS NO DATA"


def test_fix_and_moving_shows_real_speed():
    vs = VehicleStateEstimator().update(fix(raw=42.0))
    assert vs.gps == GPS_FIX and vs.speed_kmh == 42.0 and vs.moving is True
    assert vs.lat == 6.9271 and vs.heading_deg == 90.0 and vs.motion_source == "GPS+MPU"


def test_mpu_confirms_standstill_against_gps_drift():
    # Parked: GPS drift reports 3.5 km/h and the firmware even thinks "moving", MPU feels no vibration
    vs = VehicleStateEstimator().update(fix(raw=3.5, moving=True, vib=0.01))
    assert vs.speed_kmh == 0.0 and vs.moving is False and vs.motion_source == "MPU"
    assert vs.speed_status == "STATIONARY"


def test_slow_driving_with_vibration_is_not_zeroed():
    vs = VehicleStateEstimator().update(fix(raw=6.0, moving=True, vib=0.06))
    assert vs.speed_kmh == 6.0 and vs.moving is True


def test_fast_speed_trusted_even_on_very_smooth_road():
    vs = VehicleStateEstimator().update(fix(raw=60.0, moving=True, vib=0.01))
    assert vs.speed_kmh == 60.0


def test_firmware_stationary_decision_is_respected():
    vs = VehicleStateEstimator().update(fix(raw=2.5, moving=False, vib=0.05))
    assert vs.speed_kmh == 0.0 and vs.moving is False


def test_without_mpu_gps_alone_decides():
    vs = VehicleStateEstimator().update(fix(raw=3.5, moving=True, vib=0.0, mpu_connected=False))
    assert vs.speed_kmh == 3.5 and vs.motion_source == "GPS" and vs.road_text == "MPU ERROR"


def test_heading_frozen_while_stationary_and_last_fix_kept():
    est = VehicleStateEstimator()
    est.update(fix(heading=90.0), now=0.0)
    parked = est.update(fix(raw=1.0, moving=False, vib=0.01, heading=271.0), now=1.0)
    assert parked.heading_deg == 90.0  # GPS course at standstill is noise
    lost = est.update(online(satellites=2), now=11.0)
    assert lost.gps == GPS_CONNECTING and lost.lat is None and lost.speed_kmh is None
    assert (lost.last_lat, lost.last_lon) == (6.9271, 79.8612) and lost.last_fix_age_s == 10.0
