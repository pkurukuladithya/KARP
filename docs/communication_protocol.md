# KARP Communication Protocol Specification

This document defines the wire-level communication protocols between all three units in the KARP system:
1. **ESP32 <--> Raspberry Pi** (Serial UART)
2. **Raspberry Pi <--> Laptop** (WebSocket Telemetry & Control)
3. **Video Transports** (RTP/UDP/TCP Framed Streaming)

---

## 1. ESP32 <--> Raspberry Pi Protocol (Serial JSON Framing)

- **Physical Layer**: USB-CDC Serial or Hardware UART.
- **Baud Rate**: 115200 bps, 8 data bits, no parity, 1 stop bit (8N1).
- **Framing**: UTF-8 encoded single-line JSON terminated with newline `\n`.

### 1.1 ESP32 Telemetry Message (ESP32 -> Pi, Periodic 10-20 Hz)
```json
{
  "type": "sensor_telemetry",
  "seq": 1042,
  "timestamp_ms": 542310,
  "accel": {
    "valid": true,
    "ax_g": 0.04,
    "ay_g": -0.02,
    "az_g": 1.01,
    "magnitude_g": 1.011,
    "vibration_detected": false
  },
  "gps": {
    "valid": true,
    "fix_quality": 1,
    "satellites": 8,
    "latitude": 37.774929,
    "longitude": -122.419416,
    "altitude_m": 15.2,
    "speed_kmh": 42.5,
    "heading_deg": 182.4
  },
  "actuators": {
    "led_warning": false,
    "buzzer_active": false
  }
}
```

### 1.2 ESP32 Threshold Sync Command (Pi -> ESP32)
```json
{
  "type": "cmd_set_vibration_threshold",
  "threshold_g": 2.45
}
```

### 1.3 ESP32 Actuator Override Command (Pi -> ESP32)
```json
{
  "type": "cmd_actuator",
  "led": true,
  "buzzer_duration_ms": 300
}
```

### 1.4 ESP32 Acknowledgment Message (ESP32 -> Pi)
```json
{
  "type": "ack",
  "cmd": "cmd_set_vibration_threshold",
  "status": "applied",
  "active_threshold_g": 2.45
}
```

---

## 2. Raspberry Pi <--> Laptop Telemetry & Metadata Protocol (WebSocket)

- **Port**: `8765`
- **Transport**: Persistent WebSocket (Bidirectional).

### 2.1 Laptop AI Telemetry Broadcast (Laptop -> Pi, per frame @ ~30 Hz)
```json
{
  "type": "ai_telemetry",
  "frame_id": 8941,
  "timestamp_ms": 1718042910450,
  "performance": {
    "inference_fps": 34.2,
    "reception_fps": 30.1,
    "inference_latency_ms": 18.4,
    "pipeline_latency_ms": 26.1,
    "device": "NVIDIA GeForce RTX 4050 Laptop GPU (CUDA)"
  },
  "lanes": {
    "detected": true,
    "confidence": 0.92,
    "curvature_m": 850.0,
    "vehicle_offset_m": -0.12,
    "departure_warning": "NONE"
  },
  "objects": [
    {
      "id": 14,
      "class_name": "car",
      "confidence": 0.88,
      "bbox": [320, 240, 480, 410],
      "estimated_distance_m": 24.5,
      "ttc_sec": 4.8
    },
    {
      "id": 17,
      "class_name": "pedestrian",
      "confidence": 0.79,
      "bbox": [550, 290, 590, 395],
      "estimated_distance_m": 12.1,
      "ttc_sec": 2.2
    }
  ],
  "traffic_light": {
    "detected": true,
    "state": "GREEN",
    "confidence": 0.94
  },
  "traffic_signs": [
    {
      "type": "SPEED_LIMIT_50",
      "confidence": 0.86,
      "bbox": [890, 120, 940, 170]
    }
  ],
  "warnings": [
    {
      "code": "PEDESTRIAN_AHEAD",
      "level": "WARNING",
      "message": "Pedestrian near path (12.1m)"
    }
  ]
}
```

### 2.2 Client Command & Config Sync (Pi -> Laptop)
```json
{
  "type": "update_config",
  "confidence_threshold": 0.50,
  "iou_threshold": 0.45,
  "enable_distance_estimation": true
}
```

---

## 3. Video Streaming Protocol

### Frame Header (TCP Framed Fallback Protocol)
When native GStreamer RTP/UDP is unconfigured or blocked by firewall, the fallback high-speed frame protocol uses 16-byte fixed-header framing:
- Bytes 0-3: Magic `KARP` (`0x4B, 0x41, 0x52, 0x50`)
- Bytes 4-7: `frame_id` (uint32 big-endian)
- Bytes 8-11: `timestamp_ms` (uint32 big-endian)
- Bytes 12-15: `payload_length` (uint32 big-endian)
- Bytes 16 to (16 + payload_length): JPEG/H.264 encoded payload.
