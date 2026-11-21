"""
KARP Pi Brain - standalone ADAS on a Raspberry Pi 4B (camera + Pi only, no GPU, no laptop).

    python main.py                          # USB webcam 0, window on the Pi screen
    python main.py --fullscreen             # kiosk style on the car display (e.g. 3.5" 480x320 LCD)
    python main.py --view map               # start directly in Navigation Map view
    python main.py --view split             # start in Split view (ADAS Vision + Map)
    python main.py --speed 50               # set base vehicle speed (km/h)
    python main.py --web 8080               # also watch at http://<pi-ip>:8080 from a phone
    python main.py --source picam           # Raspberry Pi CSI camera module
    python main.py --source road.mp4        # replay a dash-cam video
    python main.py --source synthetic       # no camera: generated test road
    python main.py --headless --web 8080    # no monitor attached

Controls:
    Mouse Click / Touch: Cycle views (VISION -> MAP -> SPLIT)
    Key 'm': Cycle views (VISION -> MAP -> SPLIT)
    Key 'q' / 'Esc': Quit
    Key 'f': Fullscreen toggle
    Key 'd': Detection on/off
    Key 'l': Lanes on/off
    Key 's': Snapshot
"""

from __future__ import annotations
import argparse
import logging
import signal
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import cv2  # noqa: E402

from brain.alerts import AlertManager, evaluate  # noqa: E402
from brain.camera import Camera  # noqa: E402
from brain.config import load_config  # noqa: E402
from brain.detector import YoloDetector, model_files_present  # noqa: E402
from brain.engine import DetectorWorker, read_cpu_temp  # noqa: E402
from brain import hud  # noqa: E402
from brain.lanes import LaneDetector  # noqa: E402
from brain.map_view import MapView  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(name)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("pi_brain")

WINDOW = "KARP Pi Brain"
VIEW_MODES = ["vision", "map", "split"]


def parse_args():
    ap = argparse.ArgumentParser(description="KARP standalone Pi ADAS (lane + object detection + map)")
    ap.add_argument("--config", help="Path to config.json (default: pi_brain/config.json)")
    ap.add_argument("--source", help="0 | /dev/video0 | picam | <video file> | synthetic")
    ap.add_argument("--width", type=int, help="Camera capture width (e.g. 640)")
    ap.add_argument("--height", type=int, help="Camera capture height (e.g. 480)")
    ap.add_argument("--disp-width", type=int, help="Display output width (default: 480 for 3.5\" LCD)")
    ap.add_argument("--disp-height", type=int, help="Display output height (default: 320 for 3.5\" LCD)")
    ap.add_argument("--view", choices=VIEW_MODES, help="Initial view mode: vision | map | split")
    ap.add_argument("--speed", type=float, help="Base vehicle speed in km/h (hardcoded/simulated)")
    ap.add_argument("--backend", help="auto | ncnn | onnxruntime | opencv")
    ap.add_argument("--threads", type=int, help="CPU threads for the detector (Pi 4B: 3)")
    ap.add_argument("--no-detect", action="store_true", help="Lanes only")
    ap.add_argument("--no-lanes", action="store_true", help="Objects only")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--headless", action="store_true", help="No window (use with --web)")
    ap.add_argument("--web", type=int, metavar="PORT", help="Serve the HUD as MJPEG on this port")
    ap.add_argument("--duration", type=float, default=0, help="Exit after N seconds (testing)")
    return ap.parse_args()


def apply_args(cfg: dict, a) -> None:
    if a.source is not None:
        cfg["camera"]["source"] = a.source
    if a.width:
        cfg["camera"]["width"] = a.width
    if a.height:
        cfg["camera"]["height"] = a.height
    if a.disp_width:
        cfg["display"]["width"] = a.disp_width
    if a.disp_height:
        cfg["display"]["height"] = a.disp_height
    if a.view:
        cfg["display"]["mode"] = a.view
    if a.speed is not None:
        cfg.setdefault("telemetry", {})["speed_kmh"] = a.speed
    if a.backend:
        cfg["detector"]["backend"] = a.backend
    if a.threads:
        cfg["detector"]["threads"] = a.threads
    if a.no_detect:
        cfg["detector"]["enabled"] = False
    if a.no_lanes:
        cfg["lanes"]["enabled"] = False
    if a.fullscreen:
        cfg["display"]["fullscreen"] = True
    if a.headless:
        cfg["display"]["window"] = False
    if a.web is not None:
        cfg["display"]["web_port"] = a.web


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    apply_args(cfg, args)
    cv2.setNumThreads(1)  # detector backend owns the cores; OpenCV helpers stay single-threaded

    cam_cfg = cfg["camera"]
    disp_cfg = cfg["display"]
    telem_cfg = cfg.get("telemetry", {})

    target_disp_w = int(disp_cfg.get("width", 480))
    target_disp_h = int(disp_cfg.get("height", 320))

    camera = Camera(cam_cfg["source"], cam_cfg["width"], cam_cfg["height"], cam_cfg["fps"])
    camera.start()

    # Object detection (background thread)
    worker = None
    if cfg["detector"]["enabled"]:
        err = model_files_present(cfg["detector"])
        if err:
            log.error(err)
            return 2
        log.info("Loading detector (auto mode benchmarks the available backends)...")
        detector = YoloDetector(cfg["detector"])
        worker = DetectorWorker(camera, detector, cfg["geometry"])
        worker.start()

    lanes_on = bool(cfg["lanes"]["enabled"])
    lane_det = LaneDetector(cfg["lanes"])
    alert_mgr = AlertManager(cfg["alerts"]["hold_s"])

    # Navigation & Map view
    map_view = MapView(
        width=target_disp_w,
        height=target_disp_h,
        lat=telem_cfg.get("latitude", 6.9271),
        lon=telem_cfg.get("longitude", 79.8612),
        base_speed=telem_cfg.get("speed_kmh", 48.0),
    )

    # Active view mode state
    view_state = {"mode": disp_cfg.get("mode", "vision")}

    def on_mouse_click(event, x, y, flags, param):
        """Clicking or tapping anywhere on screen cycles view modes."""
        if event == cv2.EVENT_LBUTTONDOWN:
            curr = view_state["mode"]
            idx = (VIEW_MODES.index(curr) + 1) % len(VIEW_MODES) if curr in VIEW_MODES else 0
            view_state["mode"] = VIEW_MODES[idx]
            log.info(f"Screen tapped/clicked -> switched to {view_state['mode'].upper()} mode")

    web = None
    if disp_cfg["web_port"]:
        from brain.web_view import WebView

        web = WebView(int(disp_cfg["web_port"]), int(disp_cfg["web_fps"]), int(disp_cfg["web_quality"]))
        web.start()

    show = bool(disp_cfg["window"])
    if show:
        try:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(WINDOW, on_mouse_click)
            if disp_cfg["fullscreen"]:
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            else:
                cv2.resizeWindow(WINDOW, target_disp_w, target_disp_h)
        except cv2.error as e:
            log.error(f"Cannot open a window ({e.msg.strip()}). Use --headless --web 8080, "
                      "or install opencv-python (not -headless) and run from the desktop.")
            if web is None:
                return 3
            show = False

    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))

    t_start = t_stat = t_fps = time.perf_counter()
    fps_n, disp_fps, lane_ms = 0, 0.0, 0.0
    last_id = 0
    lanes = None
    log.info(f"Running in {view_state['mode'].upper()} mode. Tap screen, click mouse, or press 'm' to switch views.")

    while not stop["flag"]:
        item = camera.wait_new(last_id, timeout=1.0)
        now = time.perf_counter()

        # Update telemetry & speed calculation
        sim_mv = telem_cfg.get("sim_movement", True)
        speed_kmh = map_view.update_telemetry(sim_movement=sim_mv)

        if item is None:
            vision_disp = hud.no_signal_frame(target_disp_w, target_disp_h, f"NO CAMERA SIGNAL ({camera.source})")
            alerts = []
        else:
            frame, last_id, _t = item
            if lanes_on:
                t0 = time.perf_counter()
                lanes = lane_det.process(frame)
                lane_ms = 0.9 * lane_ms + 0.1 * (time.perf_counter() - t0) * 1000
            else:
                lanes = None
            tracks = worker.snapshot() if worker else []
            alerts = alert_mgr.update(evaluate(tracks, lanes, frame.shape[1], cfg["alerts"]), now)

            # Draw vision HUD (preserves full ADAS capabilities)
            vision_frame = frame.copy()
            hud.draw_lanes(vision_frame, lanes)
            hud.draw_tracks(vision_frame, tracks, now)
            hud.draw_speed_badge(vision_frame, speed_kmh)

            ai = f"AI {worker.fps:4.1f}fps {worker.infer_ms:3.0f}ms {worker.detector.backend}" if worker and worker.enabled else "AI off"
            ln = ("LANE " + ("OK" if lanes.stable else ("L" if lanes.left is not None else "-") +
                             ("R" if lanes.right is not None else "-"))) if lanes else "LANE off"
            temp = read_cpu_temp()
            hud.draw_status(vision_frame, f"CAM {camera.capture_fps:4.1f} | VIEW {disp_fps:4.1f} | {ai} | {ln}"
                                          + (f" | {temp:.0f}C" if temp else ""))
            hud.draw_view_mode_pill(vision_frame, view_state["mode"])
            hud.draw_alerts(vision_frame, alerts)

            # Scale vision frame to fit target 480x320 LCD perfectly
            vision_disp = cv2.resize(vision_frame, (target_disp_w, target_disp_h), interpolation=cv2.INTER_LINEAR)

        # Select view based on active mode
        mode = view_state["mode"]
        if mode == "map":
            view = map_view.render(speed_kmh, alerts, mode)
        elif mode == "split":
            view = map_view.render_split(vision_disp, speed_kmh, alerts)
        else:  # default "vision"
            view = vision_disp

        if web is not None:
            web.publish(view)
        if show:
            cv2.imshow(WINDOW, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("m"):
                curr = view_state["mode"]
                idx = (VIEW_MODES.index(curr) + 1) % len(VIEW_MODES) if curr in VIEW_MODES else 0
                view_state["mode"] = VIEW_MODES[idx]
                log.info(f"Key 'm' pressed -> switched to {view_state['mode'].upper()} mode")
            elif key == ord("f"):
                full = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_NORMAL if full else cv2.WINDOW_FULLSCREEN)
            elif key == ord("d") and worker:
                worker.enabled = not worker.enabled
            elif key == ord("l"):
                lanes_on = not lanes_on
            elif key == ord("s"):
                name = BASE_DIR / f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(str(name), view)
                log.info(f"Saved {name}")

        fps_n += 1
        if now - t_fps >= 1.0:
            disp_fps, fps_n, t_fps = fps_n / (now - t_fps), 0, now
        if now - t_stat >= 5.0:
            temp = read_cpu_temp()
            log.info(
                f"STATUS | mode {view_state['mode'].upper()} | camera {camera.capture_fps:4.1f} fps ({camera.description}) | display {disp_fps:4.1f} fps"
                + (f" | AI {worker.fps:4.1f} fps, {worker.infer_ms:.0f} ms/inference, result age {worker.age_ms:.0f} ms"
                   f" [{worker.detector.backend}]" if worker else "")
                + f" | lanes {lane_ms:.1f} ms | speed {speed_kmh:.1f} km/h" + (f" | CPU {temp:.0f}C" if temp else "")
            )
            if temp and temp > 80:
                log.warning("CPU above 80C - the Pi is throttling. Fit a heatsink + fan.")
            t_stat = now
        if args.duration and now - t_start > args.duration:
            break

    log.info("Shutting down...")
    camera.stop()
    if worker:
        worker.stop()
    if web:
        web.stop()
    if show:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
