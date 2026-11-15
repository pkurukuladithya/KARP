"""
Video Stream Sender (Pi -> Laptop).

Transmits front-camera frames to the laptop perception engine with ACK-based flow
control (bounded latency). Accepts either ready-made JPEG bytes straight from the
camera's MJPEG stream (zero re-encoding on the Pi) or BGR frames (encoded here).
"""

from __future__ import annotations
import logging
import queue
import socket
import time
from typing import Optional, Union
from PySide6.QtCore import QThread, Signal
import cv2
import numpy as np

from shared.protocols.framing import AckWindow, encode_video_frame

logger = logging.getLogger("KARP.StreamSender")

FramePayload = Union[np.ndarray, bytes]


class RpiStreamSender(QThread):
    connection_changed = Signal(bool)
    stats_updated = Signal(float, int)  # (tx_fps, dropped_frames)

    def __init__(
        self,
        laptop_ip: str = "127.0.0.1",
        port: int = 5000,
        quality: int = 80,
        max_inflight: int = 2,
        parent=None,
    ):
        super().__init__(parent)
        self.laptop_ip = laptop_ip
        self.port = port
        self.quality = quality
        self._running = True
        # 1 slot: the sender only ever holds the newest frame
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._dropped_frames = 0
        self._retarget = False
        self._window = AckWindow(max_inflight=max_inflight)

    def set_laptop_ip(self, ip: str) -> None:
        """Thread-safe: switch the laptop target (e.g. after LAN discovery)."""
        if ip and ip != self.laptop_ip:
            logger.info(f"Laptop video target changed {self.laptop_ip} -> {ip}")
            self.laptop_ip = ip
            self._retarget = True

    def stop(self) -> None:
        self._running = False
        self.wait(1000)

    def push_frame(self, frame: FramePayload, frame_id: int, timestamp_ms: int) -> None:
        """Called from the camera thread. `frame` is JPEG bytes or a BGR ndarray. Keeps only the newest."""
        item = (frame, frame_id, timestamp_ms)
        try:
            self._frame_queue.put_nowait(item)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()
                self._dropped_frames += 1
            except queue.Empty:
                pass
            try:
                self._frame_queue.put_nowait(item)
            except queue.Full:
                pass

    def _to_jpeg(self, frame: FramePayload) -> Optional[bytes]:
        if isinstance(frame, (bytes, bytearray, memoryview)):
            return bytes(frame)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
        return buf.tobytes() if ok else None

    def run(self) -> None:
        sock: Optional[socket.socket] = None
        is_connected = False
        frame_count = 0
        last_stat_time = time.time()
        last_fail_log = 0.0

        while self._running:
            if self._retarget and sock is not None:
                sock.close()
                sock = None
            self._retarget = False

            if sock is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(2.0)
                    sock.connect((self.laptop_ip, self.port))
                    self._window.reset()
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

            try:
                # Flow control: wait for ACKs while the window is full (newest frame keeps replacing the pending one)
                self._window.poll(sock, 0.0)
                if self._window.full:
                    self._window.poll(sock, 0.05)
                    continue

                try:
                    frame, frame_id, timestamp_ms = self._frame_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                jpeg = self._to_jpeg(frame)
                if not jpeg:
                    continue
                sock.sendall(encode_video_frame(frame_id, timestamp_ms, jpeg))
                self._window.on_sent()

                frame_count += 1
                now = time.time()
                if now - last_stat_time >= 1.0:
                    self.stats_updated.emit(frame_count / (now - last_stat_time), self._dropped_frames)
                    frame_count = 0
                    last_stat_time = now

            except Exception as e:
                logger.warning(f"Video link to laptop reset: {e}")
                if sock:
                    sock.close()
                    sock = None
                is_connected = False
                self.connection_changed.emit(False)
                time.sleep(0.5)

        if sock:
            sock.close()
        self.connection_changed.emit(False)
