"""
Laptop "brain" auto-discovery worker (Pi side).
Listens for the laptop's UDP beacon and reports its IP so the video sender and
metadata client can follow it automatically.
"""

from __future__ import annotations
import logging
from PySide6.QtCore import QThread, Signal

from shared.protocols.discovery import DISCOVERY_PORT, listen_for_brain

logger = logging.getLogger("KARP.BrainDiscovery")


class BrainDiscoveryWorker(QThread):
    brain_found = Signal(str)  # laptop IP

    def __init__(self, port: int = DISCOVERY_PORT, parent=None):
        super().__init__(parent)
        self.port = port
        self._running = True
        self._last_ip = ""

    def stop(self) -> None:
        self._running = False
        self.wait(1500)

    def run(self) -> None:
        while self._running:
            found = listen_for_brain(timeout_s=1.0, port=self.port)
            if found:
                ip, _beacon = found
                if ip != self._last_ip:
                    logger.info(f"Discovered laptop AI brain at {ip}")
                    self._last_ip = ip
                    self.brain_found.emit(ip)
