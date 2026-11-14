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


@dataclass
class FrameHeader:
    frame_id: int
    timestamp_ms: int
    payload_length: int


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
        return FrameHeader(
            frame_id=frame_id,
            timestamp_ms=timestamp_ms,
            payload_length=payload_len,
        )
    except Exception:
        return None


class JsonLineCodec:
    """
    Stream buffer for line-delimited JSON.
    Accumulates incoming byte chunks and yields complete newline-terminated strings.
    """

    def __init__(self, encoding: str = "utf-8"):
        self._buffer = bytearray()
        self._encoding = encoding

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
        return lines

    def clear(self) -> None:
        self._buffer.clear()
