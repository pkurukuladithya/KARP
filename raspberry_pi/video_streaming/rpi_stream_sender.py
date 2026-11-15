"""
Video Stream Broadcaster (Pi -> Laptop).
Transmits raw front-camera footage over the local network to the laptop perception engine.
"""

from __future__ import annotations
import logging
import queue
import socket
import time
from typing import Optional
from PySide6.QtCore import QThread, Signal
import cv2
import numpy as np

from shared.protocols.framing import encode_video_frame

logger = logging.getLogger("KARP.StreamSender")


class RpiStreamSender(QThread):
    connection_changed = Signal(bool)
    stats_updated = Signal(float, int)  # (tx_fps, dropped_frames)

    def __init__(
        self,
        laptop_ip: str = "127.0.0.1",
        port: int = 5000,
        quality: int = 80,
        parent=None,
    ):
        super().__init__(parent)
        self.laptop_ip = laptop_ip
        self.port = port
        self.quality = quality
        self._running = True
        self._frame_queue: queue.Queue = queue.Queue(maxsize=2)
        self._dropped_frames = 0
        self._retarget = False

    def set_laptop_ip(self, ip: str) -> None:
        """Thread-safe: switch the laptop target (e.g. after LAN discovery)."""
        if ip and ip != self.laptop_ip:
            logger.info(f"Laptop video target changed {self.laptop_ip} -> {ip}")
            self.laptop_ip = ip
            self._retarget = True

    def stop(self) -> None:
        self._running = False
        self.wait(1000)

    def push_frame(self, frame_bgr: np.ndarray, frame_id: int, timestamp_ms: int) -> None:
        """Pushes a captured frame (called from the camera thread); drops the oldest if full."""
        try:
            self._frame_queue.put_nowait((frame_bgr, frame_id, timestamp_ms))
        except queue.Full:
            self._dropped_frames += 1
            # Discard oldest to keep fresh frames
            try:
                _ = self._frame_queue.get_nowait()
                self._frame_queue.put_nowait((frame_bgr, frame_id, timestamp_ms))
            except Exception:
                pass

    def run(self) -> None:
        sock: Optional[socket.socket] = None
        is_connected = False
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]

        frame_count = 0
        last_stat_time = time.time()

        last_fail_log = 0.0
        while self._running:
            if self._retarget and sock is not None:
                sock.close()
                sock = None
            self._retarget = False

            # Reconnect if needed
            if sock is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(2.0)
                    sock.connect((self.laptop_ip, self.port))
                    is_connected = True
                    self.connection_changed.emit(True)
                    logger.info(f"Connected to Laptop Video Receiver on {self.laptop_ip}:{self.port}")
                except Exception as e:
                    if time.time() - last_fail_log > 10.0:
                        logger.warning(
                            f"Cannot reach laptop AI video port {self.laptop_ip}:{self.port} ({e}). "
                            "Is laptop_vision/main.py running and the firewall open? Retrying..."
                        )
                        last_fail_log = time.time()
                    if is_connected:
                        is_connected = False
                        self.connection_changed.emit(False)
                    if sock:
                        sock.close()
                        sock = None
                    time.sleep(1.5)
                    continue

            # Fetch frame from queue
            try:
                frame_bgr, frame_id, timestamp_ms = self._frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # Encode and transmit
            try:
                ret, jpeg_bytes = cv2.imencode(".jpg", frame_bgr, encode_param)
                if not ret:
                    continue

                packet = encode_video_frame(frame_id, timestamp_ms, jpeg_bytes.tobytes())
                sock.sendall(packet)

                frame_count += 1
                now = time.time()
                if now - last_stat_time >= 1.0:
                    fps = frame_count / (now - last_stat_time)
                    self.stats_updated.emit(fps, self._dropped_frames)
                    frame_count = 0
                    last_stat_time = now

            except Exception as e:
                logger.warning(f"Failed to transmit frame to laptop: {e}")
                if sock:
                    sock.close()
                    sock = None
                is_connected = False
                self.connection_changed.emit(False)
                time.sleep(1.0)

        if sock:
            sock.close()
        self.connection_changed.emit(False)
