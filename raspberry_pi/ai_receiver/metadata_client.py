"""
Metadata WebSocket / TCP Client (Pi <-> Laptop).
Receives structured AI detections, lane metrics, and safety alerts asynchronously.
"""

from __future__ import annotations
import asyncio
import json
import logging
import queue
import threading
import time
from typing import Optional
from PySide6.QtCore import QThread, Signal
import websockets

from shared.protocols.message_schemas import AiTelemetry

logger = logging.getLogger("KARP.MetadataClient")


class MetadataClientWorker(QThread):
    ai_telemetry_received = Signal(object)  # AiTelemetry
    connection_changed = Signal(bool)

    def __init__(self, laptop_ip: str = "127.0.0.1", port: int = 8765, parent=None):
        super().__init__(parent)
        self.laptop_ip = laptop_ip
        self.port = port
        self._running = True
        self._tx_queue: queue.Queue = queue.Queue()

    def stop(self) -> None:
        self._running = False
        self.wait(1000)

    def set_laptop_ip(self, ip: str) -> None:
        """Switch target laptop; takes effect on the next (re)connect attempt."""
        if ip and ip != self.laptop_ip:
            logger.info(f"Laptop metadata target changed {self.laptop_ip} -> {ip}")
            self.laptop_ip = ip

    def send_config_update(self, config_dict: dict) -> None:
        msg = json.dumps({"type": "update_config", "settings": config_dict})
        self._tx_queue.put(msg)

    def run(self) -> None:
        asyncio.run(self._async_loop())

    async def _async_loop(self) -> None:
        was_connected = False
        while self._running:
            uri = f"ws://{self.laptop_ip}:{self.port}"
            try:
                async with websockets.connect(
                    uri, ping_interval=5, ping_timeout=10, open_timeout=3, max_size=4 * 1024 * 1024
                ) as ws:
                    was_connected = True
                    self.connection_changed.emit(True)
                    logger.info(f"Connected to AI Metadata WebSocket at {uri}")

                    # Run reader and writer concurrently
                    rx_task = asyncio.create_task(self._rx_loop(ws))
                    tx_task = asyncio.create_task(self._tx_loop(ws))

                    done, pending = await asyncio.wait(
                        [rx_task, tx_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()

                if was_connected:
                    logger.info("AI metadata WebSocket disconnected")
                    self.connection_changed.emit(False)
                    was_connected = False
            except Exception as e:
                if was_connected:
                    self.connection_changed.emit(False)
                    was_connected = False
                logger.debug(f"WebSocket connect to {uri} failed: {e}")
                await asyncio.sleep(2.0)

        self.connection_changed.emit(False)

    async def _rx_loop(self, ws) -> None:
        while self._running:
            try:
                msg = await ws.recv()
                telemetry = AiTelemetry.from_json(msg)
                if telemetry:
                    self.ai_telemetry_received.emit(telemetry)
            except Exception as e:
                logger.debug(f"WebSocket receive error: {e}")
                break

    async def _tx_loop(self, ws) -> None:
        while self._running:
            try:
                while not self._tx_queue.empty():
                    msg = self._tx_queue.get_nowait()
                    await ws.send(msg)
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.debug(f"WebSocket transmit error: {e}")
                break
