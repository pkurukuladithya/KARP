"""
Camera Stream Receiver on Laptop AI Service (Pi -> Laptop).
Listens on port 5000, decodes incoming video packets into raw BGR frames for deep learning inference.
"""

from __future__ import annotations
import logging
import queue
import socket
import threading
import time
from typing import Callable, Optional, Tuple
import cv2
import numpy as np

from shared.protocols.framing import (
    KARP_FRAME_MAGIC,
    KARP_HEADER_SIZE,
    decode_frame_header,
    encode_ack,
)

logger = logging.getLogger("KARP.LaptopCameraReceiver")


class CameraStreamReceiver:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        queue_size: int = 2,
        on_client_connected: Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = port
        self.on_client_connected = on_client_connected
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._reception_fps: float = 0.0
        self._dropped_frames: int = 0
        self._is_connected: bool = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_latest_frame(self, timeout: float = 0.1) -> Optional[Tuple[np.ndarray, int, int]]:
        """Returns (frame_bgr, frame_id, timestamp_ms) or None."""
        try:
            return self._frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def reception_fps(self) -> float:
        return self._reception_fps

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def _run_server(self) -> None:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            server_sock.bind((self.host, self.port))
            server_sock.listen(1)
            server_sock.settimeout(1.0)
            logger.info(f"Laptop Camera Receiver listening on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to bind video receiver port {self.port}: {e}")
            return

        frame_count = 0
        last_fps_time = time.time()

        while self._running:
            try:
                client_sock, client_addr = server_sock.accept()
                client_sock.settimeout(2.0)
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._is_connected = True
                logger.info(f"Accepted camera stream from Raspberry Pi at {client_addr}")
                if self.on_client_connected:
                    try:
                        self.on_client_connected(client_addr[0])
                    except Exception as e:
                        logger.warning(f"Error in on_client_connected callback: {e}")
            except socket.timeout:
                continue
            except Exception as e:
                logger.warning(f"Error accepting stream connection: {e}")
                time.sleep(1.0)
                continue

            buffer = bytearray()

            while self._running:
                try:
                    # 1. Read KARP header
                    while len(buffer) < KARP_HEADER_SIZE:
                        chunk = client_sock.recv(4096)
                        if not chunk:
                            raise ConnectionResetError("Pi stream disconnected")
                        buffer.extend(chunk)

                    header = decode_frame_header(bytes(buffer[:KARP_HEADER_SIZE]))
                    if header is None:
                        # Corrupted byte, advance by 1
                        buffer.pop(0)
                        continue

                    # 2. Read JPEG Payload
                    total_packet_size = KARP_HEADER_SIZE + header.payload_length
                    while len(buffer) < total_packet_size:
                        chunk = client_sock.recv(min(65536, total_packet_size - len(buffer)))
                        if not chunk:
                            raise ConnectionResetError("Pi stream disconnected")
                        buffer.extend(chunk)

                    payload = bytes(buffer[KARP_HEADER_SIZE:total_packet_size])
                    buffer = buffer[total_packet_size:]
                    # ACK immediately (before decoding) -> sender flow control
                    client_sock.sendall(encode_ack(header.frame_id))

                    # 3. Decode frame
                    nparr = np.frombuffer(payload, dtype=np.uint8)
                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if frame_bgr is not None:
                        # Push to bounded queue, discarding oldest if full
                        try:
                            self._frame_queue.put_nowait((frame_bgr, header.frame_id, header.timestamp_ms))
                        except queue.Full:
                            self._dropped_frames += 1
                            try:
                                _ = self._frame_queue.get_nowait()
                                self._frame_queue.put_nowait((frame_bgr, header.frame_id, header.timestamp_ms))
                            except Exception:
                                pass

                        frame_count += 1
                        now = time.time()
                        if now - last_fps_time >= 1.0:
                            self._reception_fps = frame_count / (now - last_fps_time)
                            frame_count = 0
                            last_fps_time = now

                except Exception as e:
                    logger.info(f"Camera stream socket reset: {e}")
                    client_sock.close()
                    self._is_connected = False
                    break

        server_sock.close()
        self._is_connected = False
