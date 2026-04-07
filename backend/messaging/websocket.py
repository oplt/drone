import asyncio
import logging
import threading
import time
from typing import Dict, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from backend.runtime import (
    TelemetryEnvelopeV1,
    TelemetryPayloadV1,
)
import orjson
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class Client:
    ws: WebSocket
    q: asyncio.Queue
    task: asyncio.Task
    connected_time: float
    client_host: str | None = None
    client_port: int | None = None
    user_agent: str | None = None


class TelemetryWebSocketManager:
    """Manages WebSocket connections for real-time telemetry broadcasting"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._running = False
        self._source_connected = False
        self._clients: dict[WebSocket, Client] = {}
        self._lock = threading.Lock()

        # Last telemetry data for new connections
        self.last_telemetry: Dict = {
            "position": {"lat": 0, "lon": 0, "alt": 0, "relative_alt": 0},
            "attitude": {"roll": 0, "pitch": 0, "yaw": 0},
            "battery": {"voltage": 0, "current": 0, "remaining": 0, "temperature": 0},
            "gps": {"satellites": 0, "hdop": None},
            "link": {"rc": None, "lte": None, "telemetry": None},
            "wind": {"speed": 0, "direction": 0},
            "failsafe": {"state": "Normal"},
            "system": {"status": "UNKNOWN"},
            "status": {
                "groundspeed": 0,
                "airspeed": 0,
                "heading": 0,
                "throttle": 0,
                "climb": 0,
            },
            "camera": {"gimbal_pitch_deg": None},
            "mode": "DISCONNECTED",
            "armed": False,
            "timestamp": 0,
        }
        self.last_telemetry_payload: TelemetryPayloadV1 | None = None
        self.last_telemetry_envelope: TelemetryEnvelopeV1 | None = None

    async def initialize(self):
        """No-op hook retained for application startup compatibility."""
        return None

    def get_last_telemetry_payload(self) -> TelemetryPayloadV1 | None:
        return self.last_telemetry_payload

    def get_last_telemetry_envelope(self) -> TelemetryEnvelopeV1 | None:
        return self.last_telemetry_envelope

    def get_last_telemetry_timestamp(self) -> float:
        if self.last_telemetry_envelope is not None:
            return self.last_telemetry_envelope.emitted_at.timestamp()
        return float(self.last_telemetry.get("timestamp") or 0.0)

    def set_runtime_active(
        self,
        *,
        running: bool,
        source_connected: bool = False,
    ) -> None:
        self._running = running
        self._source_connected = source_connected

    def source_connected(self) -> bool:
        return self._source_connected

    async def ingest_telemetry_envelope(self, envelope: TelemetryEnvelopeV1) -> None:
        self.last_telemetry_envelope = envelope
        self.last_telemetry_payload = envelope.payload
        self.last_telemetry = envelope.payload.to_legacy_snapshot(
            timestamp_s=envelope.emitted_at.timestamp(),
        )
        if self._clients:
            await self.broadcast_bytes(
                orjson.dumps(envelope.to_legacy_websocket_message())
            )

    # websocket.py (update the connect method)
    async def connect(self, websocket: WebSocket):
        """Accept and manage a new WebSocket connection"""
        try:
            # IMPORTANT: Don't call websocket.accept() here!
            # It's already called in the route handler

            # Create queue for this client
            q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10)

            async def writer():
                """Task that writes messages to this specific client"""
                try:
                    while True:
                        payload = await q.get()
                        try:
                            # Decode bytes to string for JSON validation
                            message_str = payload.decode("utf-8")

                            # Send as text message
                            await websocket.send_text(message_str)

                        except (UnicodeDecodeError, json.JSONDecodeError) as e:
                            logger.warning(f"Invalid message format: {e}")
                            continue
                        except (WebSocketDisconnect, RuntimeError):
                            break  # Connection is dead
                        except Exception as e:
                            logger.error(f"Error sending to client: {e}")
                            break

                except asyncio.CancelledError:
                    logger.debug("Writer task cancelled")
                except Exception as e:
                    logger.error(f"Writer task error: {e}")
                finally:
                    # Clean up
                    with self._lock:
                        if websocket in self._clients:
                            del self._clients[websocket]
                        self.active_connections.discard(websocket)

            # Create writer task
            task = asyncio.create_task(writer())

            client_host = getattr(getattr(websocket, "client", None), "host", None)
            client_port = getattr(getattr(websocket, "client", None), "port", None)
            try:
                user_agent = websocket.headers.get("user-agent")
            except Exception:
                user_agent = None

            with self._lock:
                self.active_connections.add(websocket)
                self._clients[websocket] = Client(
                    ws=websocket,
                    q=q,
                    task=task,
                    connected_time=time.time(),
                    client_host=client_host,
                    client_port=client_port,
                    user_agent=user_agent,
                )

            logger.info(
                "✅ WebSocket connected. Active connections: %s (client=%s:%s ua=%s)",
                len(self.active_connections),
                client_host,
                client_port,
                user_agent,
            )

            # Send initial telemetry data if available
            if self.last_telemetry["timestamp"] > 0:
                payload = orjson.dumps(
                    {"type": "telemetry", "data": self.last_telemetry}
                )
                await q.put(payload)

            # Return the writer task so the route can monitor it
            return task

        except Exception as e:
            logger.error(f"❌ Failed to setup WebSocket connection: {e}")
            raise

    async def _keep_alive(self, websocket: WebSocket, writer_task: asyncio.Task):
        """Keep the connection alive and handle disconnection"""
        try:
            # Keep connection alive by listening for messages
            while True:
                try:
                    # Wait for client message (with timeout)
                    data = await asyncio.wait_for(
                        websocket.receive_text(), timeout=30.0
                    )

                    # Handle ping messages
                    if data == "ping":
                        try:
                            await websocket.send_text("pong")
                        except Exception:
                            break  # Connection is dead

                except asyncio.TimeoutError:
                    # Send keep-alive ping
                    try:
                        await websocket.send_json(
                            {"type": "keepalive", "timestamp": time.time()}
                        )
                    except Exception:
                        break  # Connection is dead

                except WebSocketDisconnect:
                    break
                except RuntimeError as e:
                    if "after sending 'websocket.close'" in str(e):
                        break  # Connection already closed
                    raise

        except WebSocketDisconnect:
            logger.debug("WebSocket disconnected normally")
        except RuntimeError as e:
            if "after sending 'websocket.close'" in str(e):
                logger.debug("WebSocket already closed")
            else:
                logger.error(f"WebSocket runtime error: {e}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        finally:
            # Cancel writer task
            if not writer_task.done():
                writer_task.cancel()
                try:
                    await writer_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            # Clean up
            with self._lock:
                if websocket in self._clients:
                    del self._clients[websocket]
                self.active_connections.discard(websocket)

            logger.info(
                f"🔌 WebSocket disconnected. Active connections: {len(self.active_connections)}"
            )

    def disconnect(self, websocket: WebSocket):
        """Disconnect a specific WebSocket client"""
        with self._lock:
            client = self._clients.pop(websocket, None)
            self.active_connections.discard(websocket)

        if client:
            client.task.cancel()
            logger.info("Manually disconnected WebSocket")

    def _enqueue_latest(self, q: asyncio.Queue[bytes], payload: bytes):
        """Add payload to client queue, dropping old messages if queue is full"""
        try:
            if q.full():
                try:
                    q.get_nowait()  # Drop oldest message
                except asyncio.QueueEmpty:
                    pass

            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Queue still full, skip this message
            pass

    async def broadcast_bytes(self, payload: bytes):
        """Broadcast message to all connected clients"""
        if not self._clients:
            return

        with self._lock:
            clients = list(self._clients.values())

        disconnected_clients = []

        for client in clients:
            try:
                # Check if WebSocket is still connected
                if client.ws.client_state == WebSocketState.CONNECTED:
                    self._enqueue_latest(client.q, payload)
                else:
                    disconnected_clients.append(client.ws)
            except Exception as e:
                logger.error(f"Failed to broadcast to client: {e}")
                disconnected_clients.append(client.ws)

        # Clean up disconnected clients
        if disconnected_clients:
            for ws in disconnected_clients:
                self.disconnect(ws)

    async def broadcast(self, message: dict):
        """Broadcast JSON message to all connected clients"""
        try:
            payload = orjson.dumps(message)
            await self.broadcast_bytes(payload)
        except Exception as e:
            logger.error(f"Broadcast error: {e}")


# Global WebSocket manager instance
telemetry_manager = TelemetryWebSocketManager()
