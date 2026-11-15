"""
Wire-level Framing Utilities for Video Frames and Line-Delimited Serial/Socket streams.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Generator, List, Optional, Tuple

KARP_FRAME_MAGIC = b"KARP"
KARP_HEADER_FORMAT = ">4sIII"  # Magic (4B), frame_id (4B uint), timestamp_ms (4B uint), payload_len (4B uint)
KARP_HEADER_SIZE = struct.calcsize(KARP_HEADER_FORMAT)  # 16 bytes
# Upper bound for a single JPEG frame; anything larger is treated as a corrupt header
KARP_MAX_PAYLOAD = 4 * 1024 * 1024


@dataclass
class FrameHeader:
    frame_id: int
    timestamp_ms: int
    payload_length: int


def now_ms32() -> int:
    """Wall-clock milliseconds truncated to 32 bits (matches the header field width)."""
    import time
    return int(time.time() * 1000) & 0xFFFFFFFF


def ms32_age(now_ms: int, then_ms: int) -> int:
    """Age in ms between two 32-bit wrapped millisecond timestamps."""
    return ((now_ms & 0xFFFFFFFF) - (then_ms & 0xFFFFFFFF)) & 0xFFFFFFFF


def encode_video_frame(frame_id: int, timestamp_ms: int, payload: bytes) -> bytes:
    """Encodes a binary payload (JPEG or H.264 NALU) with a fixed 16-byte KARP header."""
    header = struct.pack(
        KARP_HEADER_FORMAT,
        KARP_FRAME_MAGIC,
        frame_id & 0xFFFFFFFF,
        timestamp_ms & 0xFFFFFFFF,
        len(payload),
    )
    return header + payload


def decode_frame_header(header_bytes: bytes) -> Optional[FrameHeader]:
    """Validates and parses a 16-byte KARP frame header."""
    if len(header_bytes) < KARP_HEADER_SIZE:
        return None
    try:
        magic, frame_id, timestamp_ms, payload_len = struct.unpack(
            KARP_HEADER_FORMAT, header_bytes[:KARP_HEADER_SIZE]
        )
        if magic != KARP_FRAME_MAGIC:
            return None
        if payload_len == 0 or payload_len > KARP_MAX_PAYLOAD:
            return None
        return FrameHeader(
            frame_id=frame_id,
            timestamp_ms=timestamp_ms,
            payload_length=payload_len,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Video flow control
#
# TCP never drops data: if Wi-Fi briefly can't keep up, the OS socket buffers
# silently queue SECONDS of video and the picture lags further and further behind.
# Each receiver therefore acknowledges every frame (4-byte frame_id) and each
# sender keeps at most `max_inflight` unacknowledged frames on the wire. While
# waiting, the sender's 1-slot queue keeps replacing the pending frame with the
# newest one, so latency stays bounded (~2 frames) and FPS adapts to the link.
# ---------------------------------------------------------------------------
KARP_ACK_FORMAT = ">I"
KARP_ACK_SIZE = struct.calcsize(KARP_ACK_FORMAT)  # 4 bytes


def encode_ack(frame_id: int) -> bytes:
    return struct.pack(KARP_ACK_FORMAT, frame_id & 0xFFFFFFFF)


class AckWindow:
    """Sender-side in-flight frame counter fed by receiver ACKs."""

    def __init__(self, max_inflight: int = 2, stall_timeout_s: float = 3.0):
        self.max_inflight = max_inflight
        self.stall_timeout_s = stall_timeout_s
        self.reset()

    def reset(self) -> None:
        import time
        self.inflight = 0
        self._partial = 0
        self._last_progress = time.time()

    @property
    def full(self) -> bool:
        return self.inflight >= self.max_inflight

    def on_sent(self) -> None:
        import time
        if self.inflight == 0:
            self._last_progress = time.time()
        self.inflight += 1

    def poll(self, sock, timeout_s: float = 0.0) -> None:
        """Reads any available ACKs (waits up to timeout_s). Raises ConnectionError on disconnect/stall."""
        import select
        import time
        readable, _, _ = select.select([sock], [], [], timeout_s)
        if readable:
            data = sock.recv(4096)
            if not data:
                raise ConnectionError("peer closed connection")
            total = self._partial + len(data)
            acks, self._partial = divmod(total, KARP_ACK_SIZE)
            if acks:
                self.inflight = max(0, self.inflight - acks)
                self._last_progress = time.time()
        if self.inflight > 0 and time.time() - self._last_progress > self.stall_timeout_s:
            raise ConnectionError("no ACK from receiver (link stalled)")


class JsonLineCodec:
    """
    Stream buffer for line-delimited JSON.
    Accumulates incoming byte chunks and yields complete newline-terminated strings.
    """

    def __init__(self, encoding: str = "utf-8", max_line: int = 8192):
        self._buffer = bytearray()
        self._encoding = encoding
        self._max_line = max_line

    def feed(self, data: bytes) -> List[str]:
        """Appends new bytes and returns any fully received lines."""
        lines: List[str] = []
        self._buffer.extend(data)
        while b"\n" in self._buffer:
            line_bytes, self._buffer = self._buffer.split(b"\n", 1)
            line = line_bytes.strip()
            if line:
                try:
                    lines.append(line.decode(self._encoding))
                except UnicodeDecodeError:
                    # Drop corrupted characters
                    pass
        if len(self._buffer) > self._max_line:
            self._buffer.clear()  # garbage without newline (e.g. wrong baud rate)
        return lines

    def clear(self) -> None:
        self._buffer.clear()
