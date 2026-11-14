"""
Integrated ADAS Perception Pipeline Orchestrator for Laptop AI Service.
Coordinates video reception, neural inference, lane boundary fitting, object tracking,
visual annotation, return video broadcasting, and telemetry dispatch.
"""

from __future__ import annotations
import logging
import time
from typing import Optional
import numpy as np

from shared.config.system_config import get_config
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
from laptop_vision.traffic_sign_detection.sign_detector import TrafficSignDetector
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
        self.camera_receiver = CameraStreamReceiver(host=rx_host, port=rx_port)
        self.video_broadcaster = StreamBroadcaster(target_ip=tx_target_ip, port=tx_port)
        self.ws_server = TelemetryWebSocketServer(
            host="0.0.0.0",
            port=ws_port,
            on_config_received=self._on_client_config_update,
        )

        # 2. Initialize Computer Vision & AI Modules
        self.lane_detector = PolynomialLaneDetector(
            img_width=int(self.config.get("video", "width", 1280)),
            img_height=int(self.config.get("video", "height", 720)),
        )
        self.object_detector = ADASObjectDetector(
            confidence_threshold=float(self.config.get("vision", "confidence_threshold", 0.45)),
            iou_threshold=float(self.config.get("vision", "iou_threshold", 0.45)),
            use_cuda=use_cuda,
        )
        self.sign_detector = TrafficSignDetector()
        self.traffic_light_classifier = TrafficLightClassifier()
        self.decision_engine = ADASDecisionEngine()
        self.annotator = VisualAnnotator()

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

    def stop(self) -> None:
        self.running = False
        logger.info("Stopping KARP ADAS Pipeline...")
        self.camera_receiver.stop()
        self.video_broadcaster.stop()
        self.ws_server.stop()

    def step(self, timeout: float = 0.05) -> Optional[AiTelemetry]:
        """Executes one perception cycle on the latest available frame."""
        frame_tuple = self.camera_receiver.get_latest_frame(timeout=timeout)
        if frame_tuple is None:
            return None

        frame_bgr, frame_id, rx_timestamp_ms = frame_tuple
        start_time = time.time()

        # 1. Lane Boundary & Curvature Detection
        lanes = self.lane_detector.detect(frame_bgr)

        # 2. Multi-Class Object Detection & SORT Tracking
        objects = self.object_detector.detect_and_track(frame_bgr, rx_timestamp_ms)

        # 3. Traffic Sign Recognition
        signs = self.sign_detector.detect_signs(frame_bgr)

        # 4. Traffic Light State Classification
        traffic_light = TrafficLightData(detected=False, state="UNKNOWN", confidence=0.0)
        for obj in objects:
            if obj.class_name == "traffic light":
                xmin, ymin, xmax, ymax = obj.bbox
                crop = frame_bgr[max(0, ymin) : min(frame_bgr.shape[0], ymax), max(0, xmin) : min(frame_bgr.shape[1], xmax)]
                traffic_light = self.traffic_light_classifier.classify_crop(crop, obj.bbox)
                break

        # 5. Evaluate ADAS Safety Alerts (LDW, FCW, Pedestrian, Red Light)
        warnings = self.decision_engine.evaluate_safety_events(lanes, objects, traffic_light, signs)

        # Calculate Latency & Performance FPS
        end_time = time.time()
        inference_latency_ms = (end_time - start_time) * 1000.0
        total_pipeline_latency_ms = max(0.0, float(int(time.time() * 1000) - rx_timestamp_ms))

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

    def _on_client_config_update(self, settings: dict) -> None:
        """Handles runtime configuration updates synced from Raspberry Pi GUI."""
        logger.info(f"Applying runtime config update: {settings}")
        if "confidence_threshold" in settings:
            self.object_detector.set_confidence_threshold(float(settings["confidence_threshold"]))
        if "pi_ip" in settings:
            self.video_broadcaster.set_target_ip(settings["pi_ip"])
