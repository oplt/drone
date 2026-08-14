from __future__ import annotations

from contextlib import suppress

import orjson

from backend.core.events import MissionLifecycleEnvelopeV1, TelemetryEnvelopeV1
from backend.infrastructure.messaging.websocket_publisher.constants import (
    REDIS_LAST_LIFECYCLE_KEY,
    REDIS_LAST_TELEMETRY_KEY,
)
from backend.infrastructure.messaging.websocket_publisher.helpers import _envelope_org_id
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add


class IngestMixin:
    """Telemetry and mission lifecycle envelope ingestion."""

    async def ingest_telemetry_envelope(self, envelope: TelemetryEnvelopeV1) -> None:
        with observed_span(
            "api.websocket.publish",
            mission_id=getattr(getattr(envelope, "mission", None), "mission_id", None),
            flight_id=getattr(envelope, "mission_runtime_id", None),
            **{"websocket.message_type": "telemetry"},
        ):
            self.last_telemetry_envelope = envelope
            self.last_telemetry_payload = envelope.payload
            self.last_telemetry = envelope.payload.to_legacy_snapshot(
                timestamp_s=envelope.emitted_at.timestamp(),
            )
            legacy_payload = orjson.dumps(envelope.to_legacy_websocket_message())
            if self._redis is not None:
                with suppress(Exception):
                    await self._redis.set(REDIS_LAST_TELEMETRY_KEY, legacy_payload, ex=300)
            await self._broadcast_telemetry_envelope(
                envelope,
                mission_runtime_id=envelope.mission_runtime_id,
                org_id=_envelope_org_id(envelope),
            )
            metric_add("api_websocket_messages", attrs={"message_type": "telemetry"})

    async def ingest_mission_lifecycle_envelope(self, envelope: MissionLifecycleEnvelopeV1) -> None:
        with observed_span(
            "api.websocket.publish",
            mission_id=getattr(getattr(envelope, "mission", None), "mission_id", None),
            flight_id=getattr(envelope, "mission_runtime_id", None),
            **{"websocket.message_type": str(envelope.kind)},
        ):
            self.last_mission_lifecycle_envelope = envelope
            payload = orjson.dumps({"type": envelope.kind, "data": envelope.model_dump_jsonable()})
            if self._redis is not None:
                with suppress(Exception):
                    await self._redis.set(REDIS_LAST_LIFECYCLE_KEY, payload, ex=300)
            await self.broadcast_bytes(
                payload,
                mission_runtime_id=envelope.mission_runtime_id,
                org_id=_envelope_org_id(envelope),
            )
            metric_add("api_websocket_messages", attrs={"message_type": str(envelope.kind)})

