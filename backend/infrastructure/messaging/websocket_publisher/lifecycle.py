from __future__ import annotations

import asyncio
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect

from backend.infrastructure.messaging.websocket_publisher.client import Client

logger = logging.getLogger(__name__)


class LifecycleMixin:
    """Keep-alive, disconnect, subscription, and queue helpers."""

    async def _keep_alive(self, websocket: WebSocket, writer_task: asyncio.Task):
        """Keep the connection alive and handle disconnection"""
        try:
            # Keep connection alive by listening for messages
            while True:
                try:
                    # Wait for client message (with timeout)
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                    # Handle ping messages
                    if data == "ping":
                        try:
                            await websocket.send_text("pong")
                        except Exception:
                            break  # Connection is dead

                except TimeoutError:
                    # Send keep-alive ping
                    try:
                        await websocket.send_json({"type": "keepalive", "timestamp": time.time()})
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
                with suppress(asyncio.QueueEmpty):
                    q.get_nowait()  # Drop oldest message

            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Queue still full, skip this message
            pass

    def set_client_subscription(
        self,
        websocket: WebSocket,
        *,
        mission_runtime_id: str | None,
        wire_protocol: str | None = None,
    ) -> None:
        with self._lock:
            client = self._clients.get(websocket)
            if client is None:
                return
            client.mission_runtime_id = mission_runtime_id
            if wire_protocol in {"legacy", "v1"}:
                client.wire_protocol = wire_protocol

