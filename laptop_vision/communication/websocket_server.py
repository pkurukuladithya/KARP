"""
Async WebSocket Server for AI Metadata & Telemetry (Laptop -> Pi).
Broadcasts perception results, performance stats, and receives dynamic runtime configuration updates.
"""

from __future__ import annotations
import asyncio
import json
import logging
import threading
from typing import Callable, Optional, Set
import websockets

from shared.protocols.message_schemas import AiTelemetry

logger = logging.getLogger("KARP.WebSocketServer")


class TelemetryWebSocketServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765, on_config_received: Optional[Callable[[dict], None]] = None):
        self.host = host
        self.port = port
        self.on_config_received = on_config_received
        self._connected_clients: Set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def broadcast_telemetry(self, telemetry: AiTelemetry) -> None:
        """Thread-safe method to broadcast telemetry to all connected clients."""
        if not self._connected_clients or not self._loop or not self._loop.is_running():
            return

        json_str = telemetry.to_json()
        asyncio.run_coroutine_threadsafe(self._send_to_all(json_str), self._loop)

    async def _send_to_all(self, message: str) -> None:
        if not self._connected_clients:
            return
        dead_clients = set()
        for ws in self._connected_clients:
            try:
                await ws.send(message)
            except Exception:
                dead_clients.add(ws)
        self._connected_clients.difference_update(dead_clients)

    def _run_server(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def handler(websocket):
            self._connected_clients.add(websocket)
            logger.info(f"Client connected to Telemetry WebSocket: {websocket.remote_address}")
            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        if data.get("type") == "update_config" and self.on_config_received:
                            self.on_config_received(data.get("settings", {}))
                    except Exception as e:
                        logger.warning(f"Error parsing message from client: {e}")
            except Exception as e:
                logger.debug(f"Client disconnected: {e}")
            finally:
                self._connected_clients.discard(websocket)

        async def serve():
            async with websockets.serve(handler, self.host, self.port):
                logger.info(f"Telemetry WebSocket Server listening on {self.host}:{self.port}")
                while self._running:
                    await asyncio.sleep(0.5)

        try:
            self._loop.run_until_complete(serve())
        except Exception as e:
            logger.debug(f"WebSocket server stopped: {e}")
