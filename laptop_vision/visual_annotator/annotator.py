"""
Visual Annotator Engine for KARP ADAS.
Composites deep-learning detection overlays, lane polygons, distance tags, and warning banners onto video frames.
"""

from __future__ import annotations
from typing import List, Optional, Tuple
import cv2
import numpy as np

from shared.protocols.message_schemas import (
    LaneData,
    DetectedObject,
    TrafficLightData,
    TrafficSignData,
    WarningAlert,
)


class VisualAnnotator:
    # Color palette (BGR format for OpenCV)
    COLOR_CYAN = (255, 210, 0)       # Cyan: Vehicle bounding boxes
    COLOR_GREEN = (118, 230, 0)      # Green: Safe lane, Go
    COLOR_AMBER = (3, 183, 255)      # Amber: Caution, Pedestrian
    COLOR_RED = (75, 51, 255)        # Red: Critical alert, Departure
    COLOR_YELLOW = (0, 215, 255)     # Yellow: Traffic light
    COLOR_BG_DARK = (20, 16, 12)     # Semi-transparent dark background

    def __init__(self, font_scale: float = 0.55, thickness: int = 2):
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale = font_scale
        self.thickness = thickness

    def annotate_frame(
        self,
        frame_bgr: np.ndarray,
        lanes: LaneData,
        objects: List[DetectedObject],
        traffic_light: TrafficLightData,
        traffic_signs: List[TrafficSignData],
        warnings: List[WarningAlert],
        fps: float = 0.0,
        latency_ms: float = 0.0,
        device_name: str = "GPU",
    ) -> np.ndarray:
        """Draws all visual overlays onto the frame and returns the annotated BGR image."""
        annotated = frame_bgr.copy()
        h, w = annotated.shape[:2]

        # 1. Draw Lane Boundaries & Driving Corridor Polygon
        if lanes.detected and lanes.left_lane_pts and lanes.right_lane_pts:
            self._draw_lane_corridor(annotated, lanes)

        # 2. Draw Detected Objects & Distance Overlays
        for obj in objects:
            self._draw_detected_object(annotated, obj)

        # 3. Draw Traffic Light Status Badge
        if traffic_light.detected and traffic_light.state != "UNKNOWN":
            self._draw_traffic_light_badge(annotated, traffic_light)

        # 4. Draw Traffic Sign Badges
        for sign in traffic_signs:
            self._draw_traffic_sign(annotated, sign)

        # 5. Draw Top Diagnostics HUD
        self._draw_hud_banner(annotated, fps, latency_ms, device_name, lanes)

        # 6. Draw Active Safety Warning Banner (if any)
        if warnings:
            self._draw_safety_alert_banner(annotated, warnings[0])

        return annotated

    def _draw_lane_corridor(self, frame: np.ndarray, lanes: LaneData) -> None:
        left_pts = np.array(lanes.left_lane_pts, dtype=np.int32)
        right_pts = np.array(lanes.right_lane_pts, dtype=np.int32)

        if len(left_pts) < 2 or len(right_pts) < 2:
            return

        # Create driving corridor polygon: left boundary forward, right boundary reversed
        pts = np.vstack([left_pts, np.flipud(right_pts)])

        # Translucent fill
        overlay = frame.copy()
        fill_color = self.COLOR_RED if lanes.departure_warning != "NONE" else (0, 180, 50)
        cv2.fillPoly(overlay, [pts], fill_color)
        cv2.addWeighted(overlay, 0.28, frame, 0.72, 0, frame)

        # Boundary lines
        line_color = self.COLOR_RED if lanes.departure_warning != "NONE" else self.COLOR_GREEN
        cv2.polylines(frame, [left_pts], isClosed=False, color=line_color, thickness=3)
        cv2.polylines(frame, [right_pts], isClosed=False, color=line_color, thickness=3)

    def _draw_detected_object(self, frame: np.ndarray, obj: DetectedObject) -> None:
        xmin, ymin, xmax, ymax = obj.bbox
        is_ped = obj.class_name in ("pedestrian", "bicycle")

        # Color based on hazard level
        if is_ped:
            color = self.COLOR_RED if (obj.estimated_distance_m and obj.estimated_distance_m < 15.0) else self.COLOR_AMBER
        else:
            color = self.COLOR_RED if (obj.ttc_sec and obj.ttc_sec < 2.5) else self.COLOR_CYAN

        # Bounding Box with Corner Accents
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, 2)

        corner_len = min(15, (xmax - xmin) // 4, (ymax - ymin) // 4)
        if corner_len > 3:
            # Top-left corner
            cv2.line(frame, (xmin, ymin), (xmin + corner_len, ymin), color, 4)
            cv2.line(frame, (xmin, ymin), (xmin, ymin + corner_len), color, 4)
            # Bottom-right corner
            cv2.line(frame, (xmax, ymax), (xmax - corner_len, ymax), color, 4)
            cv2.line(frame, (xmax, ymax), (xmax, ymax - corner_len), color, 4)

        # Label tag above bounding box
        label_parts = [f"#{obj.id} {obj.class_name.upper()} {int(obj.confidence * 100)}%"]
        if obj.estimated_distance_m is not None:
            label_parts.append(f"~{obj.estimated_distance_m:.1f}m (approx)")
        if obj.ttc_sec is not None:
            label_parts.append(f"TTC:{obj.ttc_sec:.1f}s")

        label_text = " | ".join(label_parts)
        (tw, th), _ = cv2.getTextSize(label_text, self.font, self.font_scale, 1)

        # Draw dark background badge for text readability
        badge_y1 = max(0, ymin - th - 8)
        badge_y2 = ymin
        cv2.rectangle(frame, (xmin, badge_y1), (xmin + tw + 8, badge_y2), (18, 22, 28), -1)
        cv2.rectangle(frame, (xmin, badge_y1), (xmin + tw + 8, badge_y2), color, 1)

        cv2.putText(frame, label_text, (xmin + 4, ymin - 4), self.font, self.font_scale, color, 1, cv2.LINE_AA)

    def _draw_traffic_light_badge(self, frame: np.ndarray, tl: TrafficLightData) -> None:
        h, w = frame.shape[:2]
        bx, by = w - 170, 50

        # Draw background pill
        cv2.rectangle(frame, (bx - 10, by - 5), (bx + 150, by + 40), (20, 24, 30), -1)
        cv2.rectangle(frame, (bx - 10, by - 5), (bx + 150, by + 40), (48, 54, 61), 1)

        color = self.COLOR_GREEN if tl.state == "GREEN" else self.COLOR_YELLOW if tl.state == "YELLOW" else self.COLOR_RED
        # Illuminated Lamp Circle
        cv2.circle(frame, (bx + 16, by + 18), 12, color, -1)
        cv2.circle(frame, (bx + 16, by + 18), 13, (255, 255, 255), 1)

        text = f"{tl.state} {int(tl.confidence * 100)}%"
        cv2.putText(frame, text, (bx + 38, by + 23), self.font, 0.5, (240, 246, 252), 1, cv2.LINE_AA)

    def _draw_traffic_sign(self, frame: np.ndarray, sign: TrafficSignData) -> None:
        xmin, ymin, xmax, ymax = sign.bbox
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), self.COLOR_AMBER, 2)
        text = sign.type.replace("_", " ")
        (tw, th), _ = cv2.getTextSize(text, self.font, 0.45, 1)
        cv2.rectangle(frame, (xmin, max(0, ymin - th - 6)), (xmin + tw + 6, ymin), (20, 24, 30), -1)
        cv2.putText(frame, text, (xmin + 3, ymin - 3), self.font, 0.45, self.COLOR_AMBER, 1, cv2.LINE_AA)

    def _draw_hud_banner(
        self,
        frame: np.ndarray,
        fps: float,
        latency_ms: float,
        device_name: str,
        lanes: LaneData,
    ) -> None:
        w = frame.shape[1]

        # Top semi-transparent HUD strip
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 36), (10, 14, 20), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        # ADAS branding
        cv2.putText(frame, "KARP ADAS GPU AI", (14, 24), self.font, 0.6, (0, 210, 255), 2, cv2.LINE_AA)

        # Performance metrics
        stats_str = f"FPS: {fps:4.1f} | Latency: {latency_ms:4.1f}ms | Device: {device_name}"
        cv2.putText(frame, stats_str, (210, 23), self.font, 0.45, (200, 210, 220), 1, cv2.LINE_AA)

        # Lane metric
        if lanes.detected:
            lane_str = f"Offset: {lanes.vehicle_offset_m:+.2f}m | Curve: {lanes.curvature_m:.0f}m"
            cv2.putText(frame, lane_str, (w - 320, 23), self.font, 0.45, (118, 230, 0), 1, cv2.LINE_AA)

    def _draw_safety_alert_banner(self, frame: np.ndarray, alert: WarningAlert) -> None:
        h, w = frame.shape[:2]
        bar_h = 42
        y1 = h - bar_h - 10
        y2 = h - 10

        bg_color = (15, 10, 75) if alert.level == "CRITICAL" else (10, 45, 75)
        border_color = self.COLOR_RED if alert.level == "CRITICAL" else self.COLOR_AMBER

        overlay = frame.copy()
        cv2.rectangle(overlay, (15, y1), (w - 15, y2), bg_color, -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (15, y1), (w - 15, y2), border_color, 2)

        icon = "[!]" if alert.level == "CRITICAL" else "[i]"
        msg = f"{icon} {alert.message.upper()}"
        (tw, th), _ = cv2.getTextSize(msg, self.font, 0.6, 2)
        tx = max(25, (w - tw) // 2)
        cv2.putText(frame, msg, (tx, y1 + int(bar_h * 0.68)), self.font, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
