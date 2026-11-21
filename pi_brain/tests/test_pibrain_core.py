"""Unit tests for the standalone Pi brain (run: python -m pytest pi_brain/tests -q)."""

import numpy as np
try:
    import pytest
except ImportError:
    pytest = None

from brain.alerts import AlertManager, Alert, evaluate
from brain.camera import synthetic_road
from brain.config import DEFAULTS, load_config
from brain.detector import Detection, postprocess
from brain.lanes import LaneDetector
from brain.tracking import DistanceEstimator, Tracker, iou_matrix

W, H = 640, 480


def _head(boxes_scores):
    """Builds a fake YOLO (84, N) output from [(cx, cy, w, h, coco_class, score)]."""
    out = np.zeros((84, len(boxes_scores)), np.float32)
    for i, (cx, cy, bw, bh, c, s) in enumerate(boxes_scores):
        out[:4, i] = (cx, cy, bw, bh)
        out[4 + c, i] = s
    return out[None]


def test_postprocess_maps_back_from_letterbox_and_nms():
    # 640x480 frame letterboxed into 320: scale 0.5, pad y = 40
    out = _head([(160, 160, 40, 30, 2, 0.9), (161, 160, 40, 30, 2, 0.8), (100, 100, 10, 20, 0, 0.9), (50, 50, 9, 9, 4, 0.99)])
    dets = postprocess(out, 0.5, (0, 40), (H, W), 0.35, 0.45)
    labels = sorted(d.label for d in dets)
    assert labels == ["car", "person"]  # duplicate car suppressed, non-ADAS class (airplane) dropped
    car = next(d for d in dets if d.label == "car")
    np.testing.assert_allclose(car.box, [280, 210, 360, 270], atol=1)


def test_lanes_found_on_synthetic_road_and_no_false_departure():
    det = LaneDetector(DEFAULTS["lanes"])
    res = None
    for k in range(8):
        res = det.process(synthetic_road(W, H, k))
    assert res.left is not None and res.right is not None
    assert res.stable
    assert res.departure == "NONE"
    assert abs(res.offset_ratio) < 0.25


def test_lane_departure_when_car_drifts():
    det = LaneDetector(DEFAULTS["lanes"])
    res = None
    for k in range(10):
        img = synthetic_road(W, H, 0)
        img = np.roll(img, -int(W * 0.22), axis=1)  # road moves left in the image = car drifted right
        img[:, -int(W * 0.22):] = (70, 70, 70)
        res = det.process(img)
    assert res.departure == "RIGHT"


def test_blank_scene_has_no_lanes():
    det = LaneDetector(DEFAULTS["lanes"])
    res = det.process(np.full((H, W, 3), 90, np.uint8))
    assert res.left is None and res.right is None and res.departure == "NONE"


def test_distance_estimator_ground_plane():
    est = DistanceEstimator(W, H, camera_height_m=1.2, pitch_deg=0.0, hfov_deg=70.0)
    near = est.estimate(np.array([300, 300, 340, 470], np.float32), "car")
    far = est.estimate(np.array([310, 230, 330, 260], np.float32), "car")
    assert 1.5 < near < 5 and far > near * 3


def test_tracker_ttc_for_approaching_car():
    tr = Tracker()
    tr.estimator = DistanceEstimator(W, H, 1.2, 0.0, 70.0)
    t, tracks = 0.0, []
    for i in range(15):
        bottom = 300 + i * 8  # car's ground contact moves down = getting closer
        half = 30 + i * 3
        box = np.array([320 - half, bottom - 2 * half, 320 + half, bottom], np.float32)
        tracks = tr.update([Detection(box, 0.9, "car")], t)
        t += 0.1
    assert len(tracks) == 1
    car = tracks[0]
    assert car.closing_speed > 1.0 and car.ttc is not None and car.ttc < 5
    alerts = evaluate(tracks, None, W, DEFAULTS["alerts"])
    assert any(a.key == "fcw" for a in alerts)


def test_tracker_keeps_ids_and_drops_lost_tracks():
    tr = Tracker(max_misses=2)
    box = np.array([100, 100, 200, 200], np.float32)
    tr.update([Detection(box, 0.9, "person")], 0.0)  # first sighting: not confirmed yet
    ids = {tr.update([Detection(box + i, 0.9, "person")], i * 0.1)[0].track_id for i in range(1, 4)}
    assert len(ids) == 1
    for i in range(4, 8):
        tr.update([], i * 0.1)
    assert tr.tracks == []


def test_iou_matrix():
    a = np.array([[0, 0, 10, 10]], np.float32)
    b = np.array([[0, 0, 10, 10], [5, 0, 15, 10], [20, 20, 30, 30]], np.float32)
    np.testing.assert_allclose(iou_matrix(a, b)[0], [1.0, 1 / 3, 0.0], atol=1e-5)


def test_alert_manager_holds_then_clears():
    m = AlertManager(hold_s=0.5)
    assert len(m.update([Alert("ldw", "WARNING", "x")], now=0.0)) == 1
    assert len(m.update([], now=0.4)) == 1
    assert m.update([], now=0.6) == []


def test_config_file_loads():
    cfg = load_config()
    assert cfg["detector"]["input_size"] == 320 and cfg["camera"]["width"] == 640
    assert cfg["display"]["width"] == 480 and cfg["display"]["height"] == 320
    assert "telemetry" in cfg and cfg["telemetry"]["speed_kmh"] == 48.0


def test_map_view_rendering_and_split():
    from brain.map_view import MapView
    from brain.alerts import Alert
    import numpy as np

    mv = MapView(width=480, height=320, lat=6.9271, lon=79.8612, base_speed=48.0)
    spd = mv.update_telemetry(sim_movement=True)
    assert 40.0 < spd < 60.0

    alerts = [Alert("fcw", "CRITICAL", "BRAKE! CAR 4.2m")]
    map_img = mv.render(spd, alerts, "MAP")
    assert map_img.shape == (320, 480, 3)

    dummy_vision = np.zeros((320, 480, 3), dtype=np.uint8)
    split_img = mv.render_split(dummy_vision, spd, alerts)
    assert split_img.shape == (320, 480, 3)


def test_hud_speed_badge():
    import numpy as np
    from brain.hud import draw_speed_badge, draw_view_mode_pill

    img = np.zeros((320, 480, 3), dtype=np.uint8)
    draw_speed_badge(img, 52.0)
    draw_view_mode_pill(img, "VISION")
    assert np.any(img > 0)


def test_real_model_detects_bus_if_available():
    pytest.importorskip("onnxruntime")
    ultralytics = pytest.importorskip("ultralytics")
    import os
    import cv2
    from brain.detector import YoloDetector, model_files_present

    if model_files_present(DEFAULTS["detector"]):
        pytest.skip("model not exported")
    img = cv2.imread(os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg"))
    det = YoloDetector({**DEFAULTS["detector"], "backend": "onnxruntime"})
    labels = [d.label for d in det.detect(img)]
    assert "bus" in labels and labels.count("person") >= 3
