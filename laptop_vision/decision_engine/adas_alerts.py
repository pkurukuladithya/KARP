"""
ADAS Safety Alert Decision Engine.
Evaluates multi-sensor perception events (LDW, FCW, Pedestrian, Red Light) and determines priority warnings.
"""

from typing import List, Optional
from shared.protocols.message_schemas import (
    LaneData,
    DetectedObject,
    TrafficLightData,
    TrafficSignData,
    WarningAlert,
)


class ADASDecisionEngine:
    def evaluate_safety_events(
        self,
        lanes: LaneData,
        objects: List[DetectedObject],
        traffic_light: TrafficLightData,
        traffic_signs: List[TrafficSignData],
        frame_width: Optional[int] = None,
    ) -> List[WarningAlert]:
        alerts: List[WarningAlert] = []

        def in_path(obj: DetectedObject) -> bool:
            """True if the object's ground contact overlaps the central driving corridor."""
            if not frame_width:
                return True
            left, right = 0.30 * frame_width, 0.70 * frame_width
            return obj.bbox[2] >= left and obj.bbox[0] <= right

        # 1. Forward Collision Warning (FCW)
        for obj in objects:
            if obj.class_name in ("car", "truck", "bus", "motorcycle") and in_path(obj):
                if obj.ttc_sec is not None and obj.ttc_sec <= 2.2:
                    alerts.append(
                        WarningAlert(
                            code="FORWARD_COLLISION",
                            level="CRITICAL",
                            message=f"COLLISION IMMINENT — BRAKE! (TTC: {obj.ttc_sec:.1f}s)",
                        )
                    )
                    break
                elif obj.estimated_distance_m is not None and obj.estimated_distance_m <= 7.0:
                    alerts.append(
                        WarningAlert(
                            code="CLOSE_VEHICLE",
                            level="WARNING",
                            message=f"VEHICLE AHEAD CLOSE ({obj.estimated_distance_m:.1f}m)",
                        )
                    )

        # 2. Pedestrian Collision Hazard
        for obj in objects:
            if obj.class_name in ("pedestrian", "bicycle") and in_path(obj):
                if obj.estimated_distance_m is not None and obj.estimated_distance_m <= 15.0:
                    alerts.append(
                        WarningAlert(
                            code="PEDESTRIAN_HAZARD",
                            level="CRITICAL",
                            message=f"PEDESTRIAN IN PATH ({obj.estimated_distance_m:.1f}m)",
                        )
                    )
                    break

        # 3. Lane Departure Warning (LDW)
        if lanes.detected and lanes.departure_warning != "NONE":
            alerts.append(
                WarningAlert(
                    code="LANE_DEPARTURE",
                    level="CRITICAL",
                    message=f"LANE DEPARTURE WARNING — DRIFTING {lanes.departure_warning}!",
                )
            )

        # 4. Red Traffic Light
        if traffic_light.detected and traffic_light.state == "RED":
            alerts.append(
                WarningAlert(
                    code="RED_LIGHT",
                    level="WARNING",
                    message=f"RED TRAFFIC LIGHT DETECTED ({traffic_light.confidence*100:.0f}%)",
                )
            )

        # 5. Traffic Sign Awareness
        for sign in traffic_signs:
            alerts.append(
                WarningAlert(
                    code="SIGN_AWARENESS",
                    level="INFO",
                    message=f"SIGN DETECTED: {sign.type.replace('_', ' ')}",
                )
            )

        # Priority Sort: CRITICAL > WARNING > INFO
        priority_map = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        alerts.sort(key=lambda a: priority_map.get(a.level, 3))
        return alerts
