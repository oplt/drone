from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

import orjson
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from backend.core.events import TelemetryEnvelopeV1
from backend.infrastructure.messaging.websocket_publisher.client import Client
from backend.infrastructure.messaging.websocket_publisher.constants import REDIS_CHANNEL
from backend.infrastructure.messaging.websocket_publisher.metrics import _record_telemetry_redis_fallback

logger = logging.getLogger(__name__)


class BroadcastMixin:
    """Local and Redis-backed fan-out to connected clients."""

    async def _broadcast_telemetry_envelope(
        self,
        envelope: TelemetryEnvelopeV1,
        *,
        mission_runtime_id: str | None = None,
        org_id: int | None = None,
    ) -> None:
        legacy_payload = orjson.dumps(envelope.to_legacy_websocket_message())
        if self._redis is not None:
            try:
                redis_envelope = orjson.dumps(
                    {
                        "v": 1,
                        "f": {"m": mission_runtime_id, "o": org_id},
                        "d": orjson.loads(legacy_payload),
                    }
                )
                await self._redis.publish(REDIS_CHANNEL, redis_envelope)
                return
            except Exception as exc:
                _record_telemetry_redis_fallback("publish_failed")
                logger.warning("Redis publish failed, falling back to local broadcast: %s", exc)
        await self._local_broadcast_telemetry(
            envelope,
            mission_runtime_id=mission_runtime_id,
            org_id=org_id,
        )

    async def _local_broadcast_telemetry(
        self,
        envelope: TelemetryEnvelopeV1,
        *,
        mission_runtime_id: str | None = None,
        org_id: int | None = None,
    ) -> None:
        if not self._clients:
            return

        with self._lock:
            clients = list(self._clients.values())

        disconnected_clients = []

        for client in clients:
            try:
                if not self._client_allows(
                    client,
                    mission_runtime_id=mission_runtime_id,
                    org_id=org_id,
                ):
                    continue
                if client.ws.client_state == WebSocketState.CONNECTED:
                    wire_protocol = client.wire_protocol if client.wire_protocol in {
                        "legacy",
                        "v1",
                    } else "legacy"
                    payload = orjson.dumps(
                        envelope.to_websocket_message(wire_protocol=wire_protocol)  # type: ignore[arg-type]
                    )
                    self._enqueue_latest(client.q, payload)
                else:
                    disconnected_clients.append(client.ws)
            except Exception as e:
                logger.error(f"Failed to broadcast telemetry to client: {e}")
                disconnected_clients.append(client.ws)

        if disconnected_clients:
            for ws in disconnected_clients:
                self.disconnect(ws)

    @staticmethod
    def _client_allows(
        client: Client,
        *,
        mission_runtime_id: str | None,
        org_id: int | None,
    ) -> bool:
        if org_id is not None and client.org_id is not None and client.org_id != org_id:
            return False
        if (
            mission_runtime_id
            and client.mission_runtime_id
            and client.mission_runtime_id != mission_runtime_id
        ):
            return False
        return True

    async def broadcast_bytes(
        self,
        payload: bytes,
        *,
        mission_runtime_id: str | None = None,
        org_id: int | None = None,
    ):
        """Broadcast message to connected clients via Redis (or local fallback)."""
        if self._redis is not None:
            try:
                envelope = orjson.dumps(
                    {
                        "v": 1,
                        "f": {"m": mission_runtime_id, "o": org_id},
                        "d": orjson.loads(payload),
                    }
                )
                await self._redis.publish(REDIS_CHANNEL, envelope)
                return
            except Exception as exc:
                _record_telemetry_redis_fallback("publish_failed")
                logger.warning("Redis publish failed, falling back to local broadcast: %s", exc)
        await self._local_broadcast(
            payload,
            mission_runtime_id=mission_runtime_id,
            org_id=org_id,
        )

    async def _local_broadcast(
        self,
        payload: bytes,
        *,
        mission_runtime_id: str | None = None,
        org_id: int | None = None,
    ):
        """Fan-out payload to this process's connected clients only."""
        if not self._clients:
            return

        with self._lock:
            clients = list(self._clients.values())

        disconnected_clients = []

        for client in clients:
            try:
                if not self._client_allows(
                    client,
                    mission_runtime_id=mission_runtime_id,
                    org_id=org_id,
                ):
                    continue
                if client.ws.client_state == WebSocketState.CONNECTED:
                    self._enqueue_latest(client.q, payload)
                else:
                    disconnected_clients.append(client.ws)
            except Exception as e:
                logger.error(f"Failed to broadcast to client: {e}")
                disconnected_clients.append(client.ws)

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

