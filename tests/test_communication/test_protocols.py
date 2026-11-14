import unittest
from shared.protocols.message_schemas import (
    SensorTelemetry,
    AccelData,
    GpsData,
    AiTelemetry,
    DetectedObject,
    LaneData,
    TrafficLightData,
    ThresholdCommand,
)
from shared.protocols.framing import (
    encode_video_frame,
    decode_frame_header,
    KARP_FRAME_MAGIC,
    KARP_HEADER_SIZE,
    JsonLineCodec,
)


class TestProtocols(unittest.TestCase):
    def test_sensor_telemetry_serialization(self):
        tel = SensorTelemetry(
            seq=42,
            accel=AccelData(valid=True, ax_g=0.1, ay_g=-0.2, az_g=1.05, magnitude_g=1.07),
            gps=GpsData(valid=True, fix_quality=1, satellites=7, latitude=37.7749, longitude=-122.4194, speed_kmh=45.0),
        )
        json_str = tel.to_json()
        reconstructed = SensorTelemetry.from_json(json_str)

        self.assertIsNotNone(reconstructed)
        self.assertEqual(reconstructed.seq, 42)
        self.assertTrue(reconstructed.accel.valid)
        self.assertAlmostEqual(reconstructed.accel.magnitude_g, 1.07, places=4)
        self.assertEqual(reconstructed.gps.satellites, 7)
        self.assertAlmostEqual(reconstructed.gps.speed_kmh, 45.0, places=4)

    def test_ai_telemetry_serialization(self):
        ai = AiTelemetry(
            frame_id=1001,
            lanes=LaneData(detected=True, confidence=0.88, curvature_m=650.0, vehicle_offset_m=-0.15, departure_warning="NONE"),
            objects=[
                DetectedObject(id=1, class_name="car", confidence=0.91, bbox=(100, 200, 300, 400), estimated_distance_m=18.5)
            ],
            traffic_light=TrafficLightData(detected=True, state="GREEN", confidence=0.95),
        )
        json_str = ai.to_json()
        reconstructed = AiTelemetry.from_json(json_str)

        self.assertIsNotNone(reconstructed)
        self.assertEqual(reconstructed.frame_id, 1001)
        self.assertTrue(reconstructed.lanes.detected)
        self.assertEqual(len(reconstructed.objects), 1)
        self.assertEqual(reconstructed.objects[0].class_name, "car")
        self.assertEqual(reconstructed.objects[0].estimated_distance_m, 18.5)
        self.assertEqual(reconstructed.traffic_light.state, "GREEN")

    def test_video_frame_binary_framing(self):
        payload = b"\xFF\xD8\xFF\xE0" + b"\x00" * 256  # Mock JPEG bytes
        frame_id = 9999
        ts_ms = 12345678

        packet = encode_video_frame(frame_id, ts_ms, payload)
        self.assertEqual(len(packet), KARP_HEADER_SIZE + len(payload))

        header = decode_frame_header(packet[:KARP_HEADER_SIZE])
        self.assertIsNotNone(header)
        self.assertEqual(header.frame_id, frame_id)
        self.assertEqual(header.timestamp_ms, ts_ms)
        self.assertEqual(header.payload_length, len(payload))

        # Test invalid magic
        corrupted_header = b"BADM" + packet[4:KARP_HEADER_SIZE]
        self.assertIsNone(decode_frame_header(corrupted_header))

    def test_json_line_codec(self):
        codec = JsonLineCodec()
        chunk1 = b'{"seq": 1}\n{"seq": '
        chunk2 = b'2}\n'

        lines1 = codec.feed(chunk1)
        self.assertEqual(lines1, ['{"seq": 1}'])

        lines2 = codec.feed(chunk2)
        self.assertEqual(lines2, ['{"seq": 2}'])


if __name__ == "__main__":
    unittest.main()
