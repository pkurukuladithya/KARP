import unittest
from laptop_vision.tracking.sort_tracker import SortTracker
from shared.protocols.message_schemas import DetectedObject


class TestSortTracker(unittest.TestCase):
    def test_tracker_id_persistence(self):
        tracker = SortTracker(max_age=3, min_hits=1, iou_threshold=0.3)

        # Frame 1: Car detected at (100, 200, 250, 350)
        det_f1 = [DetectedObject(id=0, class_name="car", confidence=0.9, bbox=(100, 200, 250, 350))]
        tracks_f1 = tracker.update(det_f1)
        self.assertEqual(len(tracks_f1), 1)
        assigned_id = tracks_f1[0].id

        # Frame 2: Car slightly moved to (105, 202, 255, 352)
        det_f2 = [DetectedObject(id=0, class_name="car", confidence=0.88, bbox=(105, 202, 255, 352))]
        tracks_f2 = tracker.update(det_f2)
        self.assertEqual(len(tracks_f2), 1)
        # Verify track ID persisted across frames
        self.assertEqual(tracks_f2[0].id, assigned_id)


if __name__ == "__main__":
    unittest.main()
