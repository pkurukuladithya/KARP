"""
Annotated Video Return Stream Receiver (Laptop -> Pi).
Receives processed video footage from the laptop AI co-processor and delivers QImage frames to the PySide6 GUI.
"""

from __future__ import annotations
import logging
import socket
import time
from typing import Optional
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import cv2
import numpy as np

from shared.protocols.framing import (
    KARP_FRAME_MAGIC,
    KARP_HEADER_SIZE,
    decode_frame_header,
    encode_ack,
    ms32_age,
    now_ms32,
)

logger = logging.getLogger("KARP.StreamReceiver")


class RpiStreamReceiver(QThread):
    frame_received = Signal(QImage, float, float)  # (qimage, fps, latency_ms)
    connection_changed = Signal(bool)

    def __init__(self, listen_ip: str = "0.0.0.0", listen_port: int = 5001, parent=None):
        super().__init__(parent)
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        self._running = True
        # Latest-wins delivery: don't decode/emit a new frame until the GUI consumed the last one
        self._gui_pending = False
        self._pending_since = 0.0
        self.skipped_frames = 0

    def frame_consumed(self) -> None:
        """Called (in the GUI thread) after a frame has been handed to the widgets."""
        self._gui_pending = False

    def stop(self) -> None:
        self._running = False
        self.wait(1000)

    def run(self) -> None:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            # Windows: SO_REUSEADDR would let a 2nd instance silently share this port and
            # steal connections. Exclusive bind makes a duplicate instance fail loudly instead.
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            server_sock.bind((self.listen_ip, self.listen_port))
            server_sock.listen(1)
            server_sock.settimeout(1.0)
            logger.info(f"RpiStreamReceiver listening on {self.listen_ip}:{self.listen_port}")
        except Exception as e:
            logger.error(f"Failed to bind video receiver port {self.listen_port}: {e}")
            return

        frame_count = 0
        last_stat_time = time.time()
        fps = 0.0

        while self._running:
            try:
                client_sock, client_addr = server_sock.accept()
                client_sock.settimeout(2.0)
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.connection_changed.emit(True)
                logger.info(f"Accepted return video stream connection from {client_addr}")
            except socket.timeout:
                continue
            except Exception as e:
                logger.warning(f"Error accepting connection: {e}")
                time.sleep(1.0)
                continue

            buffer = bytearray()

            while self._running:
                try:
                    # 1. Read header
                    while len(buffer) < KARP_HEADER_SIZE:
                        chunk = client_sock.recv(4096)
                        if not chunk:
                            raise ConnectionResetError("Client disconnected")
                        buffer.extend(chunk)

                    header = decode_frame_header(bytes(buffer[:KARP_HEADER_SIZE]))
                    if header is None:
                        # Corrupted stream, discard 1 byte and realign
                        buffer.pop(0)
                        continue

                    # 2. Read full payload
                    total_packet_size = KARP_HEADER_SIZE + header.payload_length
                    while len(buffer) < total_packet_size:
                        chunk = client_sock.recv(min(65536, total_packet_size - len(buffer)))
                        if not chunk:
                            raise ConnectionResetError("Client disconnected")
                        buffer.extend(chunk)

                    payload_bytes = bytes(buffer[KARP_HEADER_SIZE:total_packet_size])
                    buffer = buffer[total_packet_size:]
                    # ACK immediately (before decoding) -> sender flow control
                    client_sock.sendall(encode_ack(header.frame_id))

                    # 3. Skip (without decoding) if the GUI hasn't displayed the previous frame yet
                    now_s = time.time()
                    if self._gui_pending and now_s - self._pending_since < 0.2:
                        self.skipped_frames += 1
                        continue

                    # 4. Decode frame
                    nparr = np.frombuffer(payload_bytes, dtype=np.uint8)
                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if frame_bgr is not None:
                        # Convert in this worker thread to Format_RGB32 (fastest to paint)
                        frame_bgra = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2BGRA)
                        h, w = frame_bgra.shape[:2]
                        qimage = QImage(frame_bgra.data, w, h, 4 * w, QImage.Format_RGB32).copy()

                        # Glass-to-glass latency: header carries the Pi's own capture time
                        age = ms32_age(now_ms32(), header.timestamp_ms)
                        latency_ms = float(age) if age < 60_000 else 0.0

                        frame_count += 1
                        now = time.time()
                        if now - last_stat_time >= 1.0:
                            fps = frame_count / (now - last_stat_time)
                            frame_count = 0
                            last_stat_time = now

                        self._gui_pending = True
                        self._pending_since = time.time()
                        self.frame_received.emit(qimage, fps, latency_ms)

                except Exception as e:
                    logger.info(f"Return video stream closed/reset: {e}")
                    client_sock.close()
                    self.connection_changed.emit(False)
                    break

        server_sock.close()
        self.connection_changed.emit(False)
