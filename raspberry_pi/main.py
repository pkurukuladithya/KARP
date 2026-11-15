"""
Raspberry Pi 4 HMI & Edge Controller Main Entry Point.
Launches the PySide6 automotive instrument cluster, video streamer, receiver, and sensor controllers.
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from shared.config.system_config import get_config
from raspberry_pi.gui.windows.main_window import MainWindow
from raspberry_pi.camera.camera_capture import CameraCaptureWorker
from raspberry_pi.video_streaming.rpi_stream_sender import RpiStreamSender
from raspberry_pi.ai_receiver.stream_receiver import RpiStreamReceiver
from raspberry_pi.ai_receiver.metadata_client import MetadataClientWorker
from raspberry_pi.ai_receiver.brain_discovery import BrainDiscoveryWorker
from raspberry_pi.esp32_communication.serial_client import Esp32SerialWorker
from raspberry_pi.esp32_communication.esp32_simulator import Esp32SimulatorWorker
from raspberry_pi.sensor_processing.accelerometer_filter import RoadConditionFilter

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("KARP.Pi")


def parse_args():
    parser = argparse.ArgumentParser(description="KARP ADAS — Raspberry Pi HMI & Edge Service")
    parser.add_argument("--laptop-ip", type=str, help="IP address of the laptop AI processing engine")
    parser.add_argument("--simulation", action="store_true", help="Force synthetic simulation mode")
    parser.add_argument("--fullscreen", action="store_true", help="Launch GUI in fullscreen kiosk mode")
    parser.add_argument("--no-discovery", action="store_true", help="Disable automatic laptop discovery (use fixed --laptop-ip)")
    return parser.parse_args()


def main():
    args = parse_args()
    config = get_config()

    # Apply CLI Overrides
    if args.laptop_ip:
        config.set("network", "laptop_ip", args.laptop_ip)
    if args.simulation:
        config.set("sensors", "simulation_mode", True)
    if args.fullscreen:
        config.set("gui", "fullscreen", True)

    app = QApplication(sys.argv)
    app.setApplicationName("KARP ADAS")

    # 1. Instantiate Main Window
    window = MainWindow()
    window.show()

    # 2. Extract Configuration Values
    laptop_ip = config.get("network", "laptop_ip", "127.0.0.1")
    port_tx = int(config.get("network", "video_port_pi_to_laptop", 5000))
    port_rx = int(config.get("network", "video_port_laptop_to_pi", 5001))
    port_ws = int(config.get("network", "metadata_ws_port", 8765))

    cam_idx = int(config.get("video", "camera_index", 0))
    cam_w = int(config.get("video", "width", 1280))
    cam_h = int(config.get("video", "height", 720))
    cam_fps = int(config.get("video", "fps", 30))
    stream_w = int(config.get("video", "stream_width", 960))
    stream_h = int(config.get("video", "stream_height", 540))
    jpeg_q = int(config.get("video", "jpeg_quality", 75))

    esp_port = str(config.get("sensors", "esp32_port", "/dev/ttyUSB0"))
    baud_rate = int(config.get("sensors", "baud_rate", 115200))
    vibe_thresh = float(config.get("sensors", "vibration_threshold_g", 2.20))
    sim_mode = bool(config.get("sensors", "simulation_mode", False))

    logger.info(
        f"Starting KARP Edge Host (Laptop: {laptop_ip}, camera {cam_w}x{cam_h}@{cam_fps}, "
        f"stream {stream_w}x{stream_h} q{jpeg_q}, SimMode: {sim_mode})"
    )

    # 3. Initialize Road Condition Digital Filter
    road_filter = RoadConditionFilter(initial_threshold_g=vibe_thresh)

    # 4. Initialize Camera Acquisition Worker
    cam_worker = CameraCaptureWorker(
        camera_index=cam_idx,
        width=cam_w,
        height=cam_h,
        fps=cam_fps,
        simulation_mode=sim_mode,
        stream_width=stream_w,
        stream_height=stream_h,
    )
    cam_worker.camera_status_changed.connect(window.on_camera_status_changed)
    # Local raw preview (converted in the camera thread) shown only while AI video is absent
    cam_worker.preview_ready.connect(window.on_local_preview)

    # 5. Initialize Video Stream Sender (Pi -> Laptop). Frames are pushed directly from
    #    the camera thread (thread-safe queue), never through the GUI event loop.
    stream_sender = RpiStreamSender(laptop_ip=laptop_ip, port=port_tx, quality=jpeg_q)
    cam_worker.add_frame_sink(stream_sender.push_frame)

    # 6. Initialize Return Video Stream Receiver (Laptop -> Pi)
    stream_receiver = RpiStreamReceiver(listen_port=port_rx)
    stream_receiver.frame_received.connect(window.on_video_frame)

    # 7. Initialize AI Metadata WebSocket Client
    meta_client = MetadataClientWorker(laptop_ip=laptop_ip, port=port_ws)
    meta_client.ai_telemetry_received.connect(window.on_ai_telemetry)
    meta_client.connection_changed.connect(window.on_ai_connection_changed)

    # 8. Initialize ESP32 Serial Worker (or Simulator Worker only if --simulation is passed)
    if sim_mode:
        esp_worker = Esp32SimulatorWorker(initial_threshold_g=vibe_thresh)
    else:
        esp_worker = Esp32SerialWorker(port=esp_port, baud_rate=baud_rate)

    esp_worker.telemetry_received.connect(window.on_sensor_telemetry)
    esp_worker.connection_changed.connect(window.on_esp32_connection_changed)
    esp_worker.log_message.connect(window.tab_hardware.append_log)

    # Initialize true disconnected state on startup
    window.on_ai_connection_changed(False)
    window.on_esp32_connection_changed(False)

    # 8b. Automatic laptop discovery (UDP beacon) - follows the laptop if its IP differs/changes
    discovery = None
    if not args.no_discovery:
        discovery = BrainDiscoveryWorker(port=int(config.get("network", "discovery_port", 5005)))

        def on_brain_found(ip: str):
            stream_sender.set_laptop_ip(ip)
            meta_client.set_laptop_ip(ip)

        discovery.brain_found.connect(on_brain_found)

    # Only send the local raw preview while the annotated AI stream is not arriving
    preview_timer = QTimer()
    preview_timer.timeout.connect(lambda: setattr(cam_worker, "preview_enabled", not window.ai_video_active()))
    preview_timer.start(250)

    # 9. Connect GUI Interactive Controls
    def on_gui_threshold_change(new_thresh: float, persist: bool):
        road_filter.set_threshold(new_thresh)
        esp_worker.send_threshold(new_thresh)
        if persist:
            config.set("sensors", "vibration_threshold_g", new_thresh, save_to_disk=True)

    def on_gui_actuator_cmd(cmd_dict: dict):
        led = cmd_dict.get("led")
        buzzer_ms = cmd_dict.get("buzzer_duration_ms")
        esp_worker.send_actuator_cmd(led=led, buzzer_ms=buzzer_ms)

    def on_gui_config_updated(new_cfg: dict):
        meta_client.send_config_update(new_cfg)

    window.threshold_changed.connect(on_gui_threshold_change)
    window.actuator_override.connect(on_gui_actuator_cmd)
    window.config_updated.connect(on_gui_config_updated)

    # 10. Start Worker Threads
    cam_worker.start()
    stream_sender.start()
    stream_receiver.start()
    meta_client.start()
    esp_worker.start()
    if discovery:
        discovery.start()

    # 11. Clean Shutdown Handling
    def cleanup():
        logger.info("Shutting down worker threads...")
        cam_worker.stop()
        stream_sender.stop()
        stream_receiver.stop()
        meta_client.stop()
        esp_worker.stop()
        if discovery:
            discovery.stop()

    app.aboutToQuit.connect(cleanup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
