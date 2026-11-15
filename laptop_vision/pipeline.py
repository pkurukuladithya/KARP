"""
Integrated ADAS Perception Pipeline Orchestrator for Laptop AI Service.
Coordinates video reception, neural inference, lane boundary fitting, object tracking,
visual annotation, return video broadcasting, and telemetry dispatch.
"""

from __future__ import annotations
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import numpy as np

from shared.config.system_config import get_config
from shared.protocols.discovery import BrainBeacon, DISCOVERY_PORT
from shared.protocols.framing import now_ms32, ms32_age
from shared.protocols.message_schemas import (
    AiTelemetry,
    PerformanceStats,
    LaneData,
    DetectedObject,
    TrafficLightData,
    TrafficSignData,
)
from laptop_vision.camera_receiver.stream_receiver import CameraStreamReceiver
from laptop_vision.lane_detection.polynomial_lane_detector import PolynomialLaneDetector
from laptop_vision.object_detection.object_detector import ADASObjectDetector
from laptop_vision.traffic_light_detection.traffic_light_classifier import TrafficLightClassifier
from laptop_vision.decision_engine.adas_alerts import ADASDecisionEngine
from laptop_vision.visual_annotator.annotator import VisualAnnotator
from laptop_vision.video_encoder.stream_broadcaster import StreamBroadcaster
from laptop_vision.communication.websocket_server import TelemetryWebSocketServer

logger = logging.getLogger("KARP.Pipeline")


class ADASPipelineOrchestrator:
    def __init__(
        self,
        rx_host: str = "0.0.0.0",
        rx_port: int = 5000,
        tx_target_ip: str = "127.0.0.1",
        tx_port: int = 5001,
        ws_port: int = 8765,
        use_cuda: bool = True,
    ):
        self.config = get_config()
        self.running = False

        # 1. Initialize Network Communication Endpoints
        self.camera_receiver = CameraStreamReceiver(
            host=rx_host,
            port=rx_port,
            on_client_connected=self._on_pi_stream_connected,
        )
        self.video_broadcaster = StreamBroadcaster(
            target_ip=tx_target_ip,
            port=tx_port,
            quality=int(self.config.get("video", "jpeg_quality", 75)),
            max_width=int(self.config.get("video", "return_width", 960)),
        )
        self.beacon = BrainBeacon(
            video_port=rx_port,
            ws_port=ws_port,
            port=int(self.config.get("network", "discovery_port", DISCOVERY_PORT)),
        )
        self.ws_server = TelemetryWebSocketServer(
            host="0.0.0.0",
            port=ws_port,
            on_config_received=self._on_client_config_update,
        )

        # 2. Initialize Computer Vision & AI Modules
        self.lane_detector = PolynomialLaneDetector(
            img_width=int(self.config.get("video", "stream_width", 960)),
            img_height=int(self.config.get("video", "stream_height", 540)),
        )
        self.object_detector = ADASObjectDetector(
            model_path=str(self.config.get("vision", "model", "yolo11s.pt")),
            confidence_threshold=float(self.config.get("vision", "confidence_threshold", 0.45)),
            iou_threshold=float(self.config.get("vision", "iou_threshold", 0.45)),
            use_cuda=use_cuda and bool(self.config.get("vision", "use_cuda", True)),
            imgsz=int(self.config.get("vision", "imgsz", 640)),
            camera_height_m=float(self.config.get("vision", "camera_height_m", 1.25)),
            camera_pitch_deg=float(self.config.get("vision", "camera_pitch_deg", 2.0)),
            focal_length_px=float(self.config.get("vision", "focal_length_px", 920.0)),
        )
        self.traffic_light_classifier = TrafficLightClassifier()
        self.decision_engine = ADASDecisionEngine()
        self.annotator = VisualAnnotator()

        # Lane fitting (CPU/OpenCV) runs concurrently with YOLO (GPU); both release the GIL
        self._lane_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="LaneWorker")

        # Performance tracking metrics
        self._inference_fps = 0.0
        self._latency_ms = 0.0
        self._frame_count = 0
        self._last_fps_time = time.time()

    def start(self) -> None:
        self.running = True
        logger.info(f"Starting KARP ADAS Pipeline on device: {self.object_detector.device_name}")
        self.camera_receiver.start()
        self.video_broadcaster.start()
        self.ws_server.start()
        self.beacon.start()

    def stop(self) -> None:
        self.running = False
        logger.info("Stopping KARP ADAS Pipeline...")
        self.camera_receiver.stop()
        self.video_broadcaster.stop()
        self.ws_server.stop()
        self.beacon.stop()
        self._lane_executor.shutdown(wait=False)

    def step(self, timeout: float = 0.05) -> Optional[AiTelemetry]:
        """Executes one perception cycle on the latest available frame."""
        frame_tuple = self.camera_receiver.get_latest_frame(timeout=timeout)
        if frame_tuple is None:
            return None

        frame_bgr, frame_id, rx_timestamp_ms = frame_tuple
        start_time = time.time()

        # 1+2. Lane detection (CPU thread) in parallel with YOLO detection + SORT (GPU)
        lane_future = self._lane_executor.submit(self.lane_detector.detect, frame_bgr)
        objects = self.object_detector.detect_and_track(frame_bgr, rx_timestamp_ms)
        lanes = lane_future.result()

        # 3. Traffic Sign Recognition (YOLO 'stop sign' class)
        signs = [
            TrafficSignData(type="STOP", confidence=o.confidence, bbox=o.bbox)
            for o in objects
            if o.class_name == "stop sign"
        ]

        # 4. Traffic Light State Classification
        traffic_light = TrafficLightData(detected=False, state="UNKNOWN", confidence=0.0)
        lights = [o for o in objects if o.class_name == "traffic light"]
        if lights:
            # Classify the largest (closest) traffic light
            obj = max(lights, key=lambda o: (o.bbox[2] - o.bbox[0]) * (o.bbox[3] - o.bbox[1]))
            xmin, ymin, xmax, ymax = obj.bbox
            crop = frame_bgr[max(0, ymin) : min(frame_bgr.shape[0], ymax), max(0, xmin) : min(frame_bgr.shape[1], xmax)]
            traffic_light = self.traffic_light_classifier.classify_crop(crop, obj.bbox)

        # 5. Evaluate ADAS Safety Alerts (LDW, FCW, Pedestrian, Red Light)
        warnings = self.decision_engine.evaluate_safety_events(
            lanes, objects, traffic_light, signs, frame_width=frame_bgr.shape[1]
        )

        # Calculate Latency & Performance FPS
        end_time = time.time()
        inference_latency_ms = (end_time - start_time) * 1000.0
        # Header timestamps are 32-bit wrapped ms from the Pi clock. Only meaningful if
        # both machines are time-synced (NTP); clamp obviously-unsynced values to 0.
        age = ms32_age(now_ms32(), rx_timestamp_ms)
        total_pipeline_latency_ms = float(age) if age < 10_000 else 0.0

        self._frame_count += 1
        now = time.time()
        if now - self._last_fps_time >= 1.0:
            self._inference_fps = self._frame_count / (now - self._last_fps_time)
            self._frame_count = 0
            self._last_fps_time = now

        # 6. Render Visual Annotations
        annotated_frame = self.annotator.annotate_frame(
            frame_bgr=frame_bgr,
            lanes=lanes,
            objects=objects,
            traffic_light=traffic_light,
            traffic_signs=signs,
            warnings=warnings,
            fps=self._inference_fps,
            latency_ms=inference_latency_ms,
            device_name=self.object_detector.device_name,
        )

        # 7. Broadcast Return Annotated Stream to Raspberry Pi
        self.video_broadcaster.broadcast_frame(annotated_frame, frame_id, rx_timestamp_ms)

        # 8. Assemble & Broadcast Telemetry Metadata via WebSocket
        telemetry = AiTelemetry(
            frame_id=frame_id,
            timestamp_ms=int(time.time() * 1000),
            performance=PerformanceStats(
                inference_fps=round(self._inference_fps, 1),
                reception_fps=round(self.camera_receiver.reception_fps, 1),
                inference_latency_ms=round(inference_latency_ms, 1),
                pipeline_latency_ms=round(total_pipeline_latency_ms, 1),
                device=self.object_detector.device_name,
                dropped_frames=self.camera_receiver.dropped_frames,
            ),
            lanes=lanes,
            objects=objects,
            traffic_light=traffic_light,
            traffic_signs=signs,
            warnings=warnings,
        )

        self.ws_server.broadcast_telemetry(telemetry)
        return telemetry

    def _on_pi_stream_connected(self, client_ip: str) -> None:
        """Automatically updates the return video broadcaster target IP when the Pi connects."""
        logger.info(f"Raspberry Pi connected from {client_ip}; routing return annotated stream to {client_ip}:{self.video_broadcaster.port}")
        self.video_broadcaster.set_target_ip(client_ip)

    def _on_client_config_update(self, settings: dict) -> None:
        """Handles runtime configuration updates synced from Raspberry Pi GUI."""
        logger.info(f"Applying runtime config update: {settings}")
        if "confidence_threshold" in settings:
            self.object_detector.set_confidence_threshold(float(settings["confidence_threshold"]))

