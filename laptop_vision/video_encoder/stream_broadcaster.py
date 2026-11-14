"""
Return Video Stream Broadcaster (Laptop -> Pi).
Transmits annotated video frames to the Raspberry Pi HMI receiver on port 5001.
"""

from __future__ import annotations
import logging
import queue
import socket
import threading
import time
from typing import Optional
import cv2
import numpy as np

from shared.protocols.framing import encode_video_frame

logger = logging.getLogger("KARP.StreamBroadcaster")


class StreamBroadcaster:
    def __init__(self, target_ip: str = "127.0.0.1", port: int = 5001, quality: int = 80):
        self.target_ip = target_ip
        self.port = port
        self.quality = quality
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._queue: queue.Queue = queue.Queue(maxsize=3)
        self._is_connected = False
        self._tx_fps = 0.0

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def set_target_ip(self, ip: str) -> None:
        if self.target_ip != ip:
            self.target_ip = ip

    def broadcast_frame(self, frame_bgr: np.ndarray, frame_id: int, timestamp_ms: int) -> None:
        """Pushes an annotated frame to be sent to Raspberry Pi."""
        try:
            self._queue.put_nowait((frame_bgr, frame_id, timestamp_ms))
        except queue.Full:
            try:
                _ = self._queue.get_nowait()
                self._queue.put_nowait((frame_bgr, frame_id, timestamp_ms))
            except Exception:
                pass

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def tx_fps(self) -> float:
        return self._tx_fps

    def _run_loop(self) -> None:
        sock: Optional[socket.socket] = None
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
        frame_count = 0
        last_stat_time = time.time()

        while self._running:
            # Connect to Raspberry Pi receiver
            if sock is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(2.0)
                    sock.connect((self.target_ip, self.port))
                    self._is_connected = True
                    logger.info(f"Connected to Raspberry Pi Video Receiver at {self.target_ip}:{self.port}")
                except Exception:
                    self._is_connected = False
                    if sock:
                        sock.close()
                        sock = None
                    time.sleep(1.5)
                    continue

            # Fetch next frame
            try:
                frame_bgr, frame_id, timestamp_ms = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                ret, jpeg_bytes = cv2.imencode(".jpg", frame_bgr, encode_params)
                if not ret:
                    continue

                packet = encode_video_frame(frame_id, timestamp_ms, jpeg_bytes.tobytes())
                sock.sendall(packet)

                frame_count += 1
                now = time.time()
                if now - last_stat_time >= 1.0:
                    self._tx_fps = frame_count / (now - last_stat_time)
                    frame_count = 0
                    last_stat_time = now

            except Exception as e:
                logger.warning(f"Error streaming to Pi receiver: {e}")
                if sock:
                    sock.close()
                    sock = None
                self._is_connected = False
                time.sleep(1.0)

        if sock:
            sock.close()
        self._is_connected = False
