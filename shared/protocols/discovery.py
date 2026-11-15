"""
Zero-config LAN discovery between the Laptop "brain" and the Raspberry Pi.

The laptop broadcasts a small UDP beacon every second on DISCOVERY_PORT. The Pi
listens and learns the laptop IP from the packet's source address, so the system
keeps working even if DHCP changes the laptop's address.
"""

from __future__ import annotations
import json
import logging
import socket
import threading
import time
from typing import List, Optional, Tuple

logger = logging.getLogger("KARP.Discovery")

DISCOVERY_PORT = 5005
BEACON_TYPE = "karp_brain"


def local_ipv4_addresses() -> List[str]:
    """Best-effort list of this host's non-loopback IPv4 addresses."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    # Address used for the default route (works even if hostname resolution is poor)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packets are sent for UDP connect
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def encode_beacon(video_port: int, ws_port: int) -> bytes:
    return json.dumps({"type": BEACON_TYPE, "video_port": video_port, "ws_port": ws_port}).encode()


def decode_beacon(data: bytes) -> Optional[dict]:
    try:
        msg = json.loads(data.decode("utf-8"))
        if isinstance(msg, dict) and msg.get("type") == BEACON_TYPE:
            return msg
    except Exception:
        pass
    return None


class BrainBeacon:
    """Laptop side: periodically broadcasts presence on every local IPv4 interface."""

    def __init__(self, video_port: int, ws_port: int, port: int = DISCOVERY_PORT, interval_s: float = 1.0):
        self.payload = encode_beacon(video_port, ws_port)
        self.port = port
        self.interval_s = interval_s
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="BrainBeacon")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        sockets: List[Tuple[socket.socket, str]] = []
        last_refresh = 0.0
        while self._running:
            now = time.time()
            if now - last_refresh > 15.0:  # interfaces may come and go (Wi-Fi reconnects)
                for s, _ in sockets:
                    s.close()
                sockets = []
                for ip in local_ipv4_addresses():
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        s.bind((ip, 0))
                        subnet_bcast = ".".join(ip.split(".")[:3] + ["255"])
                        sockets.append((s, subnet_bcast))
                    except Exception:
                        continue
                last_refresh = now
            for s, bcast in sockets:
                for dst in (bcast, "255.255.255.255"):
                    try:
                        s.sendto(self.payload, (dst, self.port))
                    except Exception:
                        pass
            time.sleep(self.interval_s)
        for s, _ in sockets:
            s.close()


def listen_for_brain(timeout_s: float, port: int = DISCOVERY_PORT) -> Optional[Tuple[str, dict]]:
    """Blocks up to timeout_s waiting for a beacon. Returns (laptop_ip, beacon) or None."""
    # Only trust beacons from our own /24 (ignores virtual adapters such as VirtualBox/hotspot)
    my_subnets = {".".join(ip.split(".")[:3]) for ip in local_ipv4_addresses()}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", port))
        sock.settimeout(0.5)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            msg = decode_beacon(data)
            if not msg:
                continue
            if my_subnets and ".".join(addr[0].split(".")[:3]) not in my_subnets:
                continue
            return addr[0], msg
    except Exception as e:
        logger.debug(f"Discovery listen error: {e}")
    finally:
        sock.close()
    return None
