"""
Return Video Stream Broadcaster (Laptop -> Pi).
Transmits annotated frames to the Raspberry Pi HMI receiver on port 5001 with
ACK-based flow control (bounded latency) and optional downscaling so the Pi
never decodes more pixels than it can display.
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

from shared.protocols.framing import AckWindow, encode_video_frame

logger = logging.getLogger("KARP.StreamBroadcaster")


class StreamBroadcaster:
    def __init__(
        self,
        target_ip: str = "127.0.0.1",
        port: int = 5001,
        quality: int = 80,
        max_width: int = 0,
        max_inflight: int = 2,
    ):
        self.target_ip = target_ip
        self.port = port
        self.quality = quality
        self.max_width = max_width  # 0 = send at source resolution
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._is_connected = False
        self._tx_fps = 0.0
        self._retarget = False
        self._window = AckWindow(max_inflight=max_inflight)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ReturnVideoTx")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def set_target_ip(self, ip: str) -> None:
        if self.target_ip != ip:
            logger.info(f"Return video target changed {self.target_ip} -> {ip}")
            self.target_ip = ip
            self._retarget = True

    def broadcast_frame(self, frame_bgr: np.ndarray, frame_id: int, timestamp_ms: int) -> None:
        """Queues an annotated frame for the Pi; only the newest pending frame is kept."""
        item = (frame_bgr, frame_id, timestamp_ms)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(item)
            except queue.Full:
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
        last_fail_log = 0.0

        while self._running:
            if self._retarget and sock is not None:
                sock.close()
                sock = None
                self._is_connected = False
            self._retarget = False

            if sock is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(2.0)
                    sock.connect((self.target_ip, self.port))
                    self._window.reset()
                    self._is_connected = True
                    logger.info(f"Connected to Raspberry Pi Video Receiver at {self.target_ip}:{self.port}")
                except Exception as e:
                    self._is_connected = False
                    if time.time() - last_fail_log > 10.0:
                        logger.warning(
                            f"Cannot reach Pi HMI video receiver {self.target_ip}:{self.port} ({e}). "
                            "Is raspberry_pi/main.py running? Retrying..."
                        )
                        last_fail_log = time.time()
                    if sock:
                        sock.close()
                        sock = None
                    time.sleep(1.5)
                    continue

            try:
                self._window.poll(sock, 0.0)
                if self._window.full:
                    self._window.poll(sock, 0.05)
                    continue

                try:
                    frame_bgr, frame_id, timestamp_ms = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                h, w = frame_bgr.shape[:2]
                if self.max_width and w > self.max_width:
                    new_h = int(round(h * self.max_width / w))
                    frame_bgr = cv2.resize(frame_bgr, (self.max_width, new_h), interpolation=cv2.INTER_AREA)

                ret, jpeg_bytes = cv2.imencode(".jpg", frame_bgr, encode_params)
                if not ret:
                    continue
                sock.sendall(encode_video_frame(frame_id, timestamp_ms, jpeg_bytes.tobytes()))
                self._window.on_sent()

                frame_count += 1
                now = time.time()
                if now - last_stat_time >= 1.0:
                    self._tx_fps = frame_count / (now - last_stat_time)
                    frame_count = 0
                    last_stat_time = now

            except Exception as e:
                logger.warning(f"Return video link to Pi reset: {e}")
                if sock:
                    sock.close()
                    sock = None
                self._is_connected = False
                time.sleep(0.5)

        if sock:
            sock.close()
        self._is_connected = False
