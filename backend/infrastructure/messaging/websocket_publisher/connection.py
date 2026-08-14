from __future__ import annotations

import asyncio
import json
import logging
import time

import orjson
from fastapi import WebSocket

from backend.infrastructure.messaging.websocket_publisher.client import Client
from backend.infrastructure.messaging.websocket_publisher.helpers import _envelope_org_id
from backend.observability.metrics import add as metric_add

logger = logging.getLogger(__name__)


class ConnectionMixin:
    """WebSocket client connect and writer task setup."""

    async def connect(
        self,
        websocket: WebSocket,
        *,
        user_id: int | None = None,
        org_id: int | None = None,
    ):
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
                    metric_add("api_websocket_disconnects", attrs={"channel": "telemetry"})

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
                    user_id=user_id,
                    org_id=org_id,
                )

            logger.info(
                "✅ WebSocket connected. Active connections: %s (client=%s:%s ua=%s)",
                len(self.active_connections),
                client_host,
                client_port,
                user_agent,
            )

            # Send initial telemetry only when it belongs to this client's org.
            if self.last_telemetry["timestamp"] > 0:
                envelope_org = _envelope_org_id(self.last_telemetry_envelope) if (
                    self.last_telemetry_envelope is not None
                ) else None
                if (
                    org_id is None
                    or envelope_org is None
                    or envelope_org == org_id
                ):
                    payload = orjson.dumps({"type": "telemetry", "data": self.last_telemetry})
                    await q.put(payload)
                    metric_add(
                        "api_websocket_messages",
                        attrs={"message_type": "initial_telemetry"},
                    )

            # Return the writer task so the route can monitor it
            return task

        except Exception as e:
            logger.error(f"❌ Failed to setup WebSocket connection: {e}")
            raise

