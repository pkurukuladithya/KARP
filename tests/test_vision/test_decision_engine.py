import unittest
from laptop_vision.decision_engine.adas_alerts import ADASDecisionEngine
from shared.protocols.message_schemas import (
    LaneData,
    DetectedObject,
    TrafficLightData,
    TrafficSignData,
)


class TestDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ADASDecisionEngine()

    def test_lane_departure_alert(self):
        lanes = LaneData(detected=True, departure_warning="LEFT", vehicle_offset_m=-0.45)
        alerts = self.engine.evaluate_safety_events(lanes, [], TrafficLightData(), [])

        self.assertTrue(any(a.code == "LANE_DEPARTURE" and a.level == "CRITICAL" for a in alerts))

    def test_pedestrian_hazard_alert(self):
        lanes = LaneData(detected=True, departure_warning="NONE")
        ped = DetectedObject(id=1, class_name="pedestrian", confidence=0.85, bbox=(500, 300, 560, 420), estimated_distance_m=11.5)
        alerts = self.engine.evaluate_safety_events(lanes, [ped], TrafficLightData(), [])

        self.assertTrue(any(a.code == "PEDESTRIAN_HAZARD" and a.level == "CRITICAL" for a in alerts))

    def test_red_traffic_light_alert(self):
        tl = TrafficLightData(detected=True, state="RED", confidence=0.92)
        alerts = self.engine.evaluate_safety_events(LaneData(), [], tl, [])

        self.assertTrue(any(a.code == "RED_LIGHT" for a in alerts))


if __name__ == "__main__":
    unittest.main()
