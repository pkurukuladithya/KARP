"""
Structured message schemas for KARP ADAS.
Defines types for ESP32 serial telemetry, Laptop AI metadata, and command messages.
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AccelData:
    valid: bool = False
    ax_g: float = 0.0
    ay_g: float = 0.0
    az_g: float = 1.0
    magnitude_g: float = 1.0
    filtered_magnitude_g: float = 1.0
    vibration_detected: bool = False
    sensor_model: str = "CONFIGURABLE_I2C"


@dataclass
class GpsData:
    valid: bool = False
    fix_quality: int = 0  # 0=Invalid, 1=GPS SPS, 2=DGPS
    satellites: int = 0
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_m: float = 0.0
    speed_kmh: float = 0.0
    heading_deg: float = 0.0
    is_simulated: bool = False


@dataclass
class ActuatorState:
    led_warning: bool = False
    buzzer_active: bool = False


@dataclass
class SensorTelemetry:
    type: str = "sensor_telemetry"
    seq: int = 0
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    accel: AccelData = field(default_factory=AccelData)
    gps: GpsData = field(default_factory=GpsData)
    actuators: ActuatorState = field(default_factory=ActuatorState)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SensorTelemetry:
        accel_d = data.get("accel", {})
        gps_d = data.get("gps", {})
        act_d = data.get("actuators", {})

        return cls(
            type=data.get("type", "sensor_telemetry"),
            seq=data.get("seq", 0),
            timestamp_ms=data.get("timestamp_ms", int(time.time() * 1000)),
            accel=AccelData(**{k: v for k, v in accel_d.items() if k in AccelData.__annotations__}),
            gps=GpsData(**{k: v for k, v in gps_d.items() if k in GpsData.__annotations__}),
            actuators=ActuatorState(**{k: v for k, v in act_d.items() if k in ActuatorState.__annotations__}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> Optional[SensorTelemetry]:
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception:
            return None


@dataclass
class DetectedObject:
    id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (xmin, ymin, xmax, ymax) in pixels
    estimated_distance_m: Optional[float] = None
    ttc_sec: Optional[float] = None


@dataclass
class TrafficSignData:
    type: str  # e.g., SPEED_LIMIT_50, STOP, YIELD, PEDESTRIAN_CROSSING
    confidence: float
    bbox: Tuple[int, int, int, int]


@dataclass
class TrafficLightData:
    detected: bool = False
    state: str = "UNKNOWN"  # RED, YELLOW, GREEN, UNKNOWN
    confidence: float = 0.0
    bbox: Optional[Tuple[int, int, int, int]] = None


@dataclass
class LaneData:
    detected: bool = False
    confidence: float = 0.0
    curvature_m: float = 0.0
    vehicle_offset_m: float = 0.0  # Positive = right of center, Negative = left of center
    departure_warning: str = "NONE"  # NONE, LEFT, RIGHT
    left_lane_pts: List[Tuple[int, int]] = field(default_factory=list)
    right_lane_pts: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class WarningAlert:
    code: str  # e.g., LANE_DEPARTURE, PEDESTRIAN_AHEAD, FORWARD_COLLISION, RED_LIGHT
    level: str  # INFO, WARNING, CRITICAL
    message: str
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class PerformanceStats:
    inference_fps: float = 0.0
    reception_fps: float = 0.0
    inference_latency_ms: float = 0.0
    pipeline_latency_ms: float = 0.0
    device: str = "CPU"
    dropped_frames: int = 0


@dataclass
class AiTelemetry:
    type: str = "ai_telemetry"
    frame_id: int = 0
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    performance: PerformanceStats = field(default_factory=PerformanceStats)
    lanes: LaneData = field(default_factory=LaneData)
    objects: List[DetectedObject] = field(default_factory=list)
    traffic_light: TrafficLightData = field(default_factory=TrafficLightData)
    traffic_signs: List[TrafficSignData] = field(default_factory=list)
    warnings: List[WarningAlert] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AiTelemetry:
        perf_d = data.get("performance", {})
        lanes_d = data.get("lanes", {})
        tl_d = data.get("traffic_light", {})
        objs_d = data.get("objects", [])
        signs_d = data.get("traffic_signs", [])
        warns_d = data.get("warnings", [])

        return cls(
            type=data.get("type", "ai_telemetry"),
            frame_id=data.get("frame_id", 0),
            timestamp_ms=data.get("timestamp_ms", int(time.time() * 1000)),
            performance=PerformanceStats(**{k: v for k, v in perf_d.items() if k in PerformanceStats.__annotations__}),
            lanes=LaneData(**{k: v for k, v in lanes_d.items() if k in LaneData.__annotations__}),
            traffic_light=TrafficLightData(**{k: v for k, v in tl_d.items() if k in TrafficLightData.__annotations__}),
            objects=[DetectedObject(**{k: v for k, v in o.items() if k in DetectedObject.__annotations__}) for o in objs_d],
            traffic_signs=[TrafficSignData(**{k: v for k, v in s.items() if k in TrafficSignData.__annotations__}) for s in signs_d],
            warnings=[WarningAlert(**{k: v for k, v in w.items() if k in WarningAlert.__annotations__}) for w in warns_d],
        )

    @classmethod
    def from_json(cls, json_str: str) -> Optional[AiTelemetry]:
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception:
            return None


@dataclass
class ThresholdCommand:
    type: str = "cmd_set_vibration_threshold"
    threshold_g: float = 2.20

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class ActuatorCommand:
    type: str = "cmd_actuator"
    led: Optional[bool] = None
    buzzer_duration_ms: Optional[int] = None

    def to_json(self) -> str:
        d = {"type": self.type}
        if self.led is not None:
            d["led"] = self.led
        if self.buzzer_duration_ms is not None:
            d["buzzer_duration_ms"] = self.buzzer_duration_ms
        return json.dumps(d)


@dataclass
class ConfigUpdateCommand:
    type: str = "update_config"
    settings: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))
