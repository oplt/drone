from __future__ import annotations

import asyncio
import threading

from fastapi import WebSocket

from backend.core.events import MissionLifecycleEnvelopeV1, TelemetryEnvelopeV1, TelemetryPayloadV1
from backend.infrastructure.messaging.websocket_publisher.client import Client
from backend.infrastructure.messaging.websocket_publisher.defaults import DEFAULT_LAST_TELEMETRY


class RuntimeStateMixin:
    """Runtime flags, cached telemetry, and snapshot helpers."""

    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()
        self._running = False
        self._source_connected = False
        self._clients: dict[WebSocket, Client] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._subscriber_task: asyncio.Task | None = None
        self._shutting_down = False
        self.last_telemetry = dict(DEFAULT_LAST_TELEMETRY)
        self.last_telemetry_payload: TelemetryPayloadV1 | None = None
        self.last_telemetry_envelope: TelemetryEnvelopeV1 | None = None
        self.last_mission_lifecycle_envelope: MissionLifecycleEnvelopeV1 | None = None

    def get_last_telemetry_payload(self) -> TelemetryPayloadV1 | None:
        return self.last_telemetry_payload

    def get_last_telemetry_envelope(self) -> TelemetryEnvelopeV1 | None:
        return self.last_telemetry_envelope

    def get_last_mission_lifecycle_envelope(self) -> MissionLifecycleEnvelopeV1 | None:
        return self.last_mission_lifecycle_envelope

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

    def client_count(self) -> int:
        return len(self.active_connections)

    def runtime_snapshot(self) -> dict[str, float | int | bool]:
        return {
            "running": self._running,
            "source_connected": self._source_connected,
            "active_connections": self.client_count(),
            "last_update": self.get_last_telemetry_timestamp(),
        }

    def latest_position_snapshot(self) -> dict[str, object]:
        payload = self.last_telemetry_payload
        if payload is None:
            return {
                "has_position": False,
                "position": {
                    "lat": 0.0,
                    "lon": 0.0,
                    "alt": 0.0,
                    "relative_alt": 0.0,
                },
            }
        return {
            "has_position": payload.has_position(),
            "position": {
                "lat": float(payload.position.lat or 0.0),
                "lon": float(payload.position.lon or 0.0),
                "alt": float(payload.position.alt_m or 0.0),
                "relative_alt": float(payload.position.relative_alt_m or 0.0),
            },
        }
