from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from backend.core.events import (
    FlightEventEnvelopeV1,
    FlightEventPayloadV1,
    FlightEventSeverityV1,
    MissionLifecycleEnvelopeV1,
    MissionLifecyclePayloadV1,
    TelemetryEnvelopeV1,
    VideoHealthEnvelopeV1,
    utc_now,
)
from backend.modules.telemetry.repository import TelemetryBatcher

logger = logging.getLogger(__name__)


class RuntimeEventServiceMixin:
    async def _fanout_runtime_envelope(
        self,
        envelope: TelemetryEnvelopeV1
        | FlightEventEnvelopeV1
        | MissionLifecycleEnvelopeV1
        | VideoHealthEnvelopeV1,
    ) -> None:
        if isinstance(envelope, TelemetryEnvelopeV1):
            self._metrics["telemetry_envelopes_total"] += 1
            await self.fanout.ingest_telemetry_envelope(envelope)
            if self.mqtt:
                self.mqtt.publish(
                    "drone/runtime/telemetry",
                    envelope.model_dump_jsonable(),
                    qos=1,
                )
            if self._telemetry_batcher is not None:
                row = TelemetryBatcher.row_from_envelope(envelope)
                if row is not None:
                    await self._telemetry_batcher.add(row)
            return

        if self.mqtt:
            self.mqtt.publish(
                f"drone/runtime/{envelope.kind}",
                envelope.model_dump_jsonable(),
                qos=1,
            )
        if isinstance(envelope, MissionLifecycleEnvelopeV1):
            await self.fanout.ingest_mission_lifecycle_envelope(envelope)
        else:
            await self.fanout.broadcast(
                {
                    "type": envelope.kind,
                    "data": envelope.model_dump_jsonable(),
                }
            )

    async def record_flight_event(
        self,
        event_type: str,
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None = None,
        *,
        flight_id: int | None = None,
        source: str = "mission.runtime",
        category: str | None = None,
        severity: FlightEventSeverityV1 | None = None,
    ) -> FlightEventEnvelopeV1:
        persisted_data = self._serialize_event_data(data)
        target_flight_id = flight_id if flight_id is not None else self._flight_id

        if isinstance(data, FlightEventPayloadV1):
            payload = data
        else:
            payload = FlightEventPayloadV1(
                event_name=event_type,
                category=category,
                severity=severity,
                attributes=persisted_data,
            )

        envelope = FlightEventEnvelopeV1(
            mission_runtime_id=self._current_mission_runtime_id(),
            db_flight_id=target_flight_id,
            sequence=self._sequence(source),
            emitted_at=utc_now(),
            source=source,
            mission=self._mission_context(),
            payload=payload,
        )
        # Fan-out to websocket/MQTT first — never blocked by DB latency.
        await self._fanout_runtime_envelope(envelope)

        if target_flight_id is not None:
            # New path: enqueue DB write; drop-oldest on overflow.
            self._enqueue_db_event(target_flight_id, event_type, persisted_data)
            # Shadow path (only when ORCHESTRATOR_SHADOW_MODE=true): also run the
            # old direct write so both paths can be observed simultaneously.
            self._maybe_schedule_shadow_write(target_flight_id, event_type, persisted_data)

        return envelope

    async def record_mission_lifecycle(
        self,
        payload: MissionLifecyclePayloadV1 | dict[str, Any] | Mapping[str, Any],
        *,
        flight_id: int | None = None,
        source: str = "orchestrator.lifecycle",
    ) -> MissionLifecycleEnvelopeV1:
        lifecycle_payload = (
            payload
            if isinstance(payload, MissionLifecyclePayloadV1)
            else MissionLifecyclePayloadV1.model_validate(payload)
        )
        target_flight_id = flight_id if flight_id is not None else self._flight_id

        envelope = MissionLifecycleEnvelopeV1(
            mission_runtime_id=self._current_mission_runtime_id(),
            db_flight_id=target_flight_id,
            sequence=self._sequence(source),
            emitted_at=utc_now(),
            source=source,
            mission=self._mission_context(),
            payload=lifecycle_payload,
        )
        # Fan-out first — never blocked by DB.
        await self._fanout_runtime_envelope(envelope)

        # Lifecycle events are critical — never drop. Use the dedicated lifecycle
        # queue which blocks briefly if full rather than silently discarding.
        if target_flight_id is not None:
            serialized = self._serialize_event_data(lifecycle_payload)
            await self._enqueue_lifecycle_event(
                target_flight_id, "mission_state_changed", serialized
            )
            # Shadow path: also run old direct write for comparison when enabled.
            self._maybe_schedule_shadow_write(target_flight_id, "mission_state_changed", serialized)

        return envelope

    async def record_persisted_event(
        self,
        event_type: str,
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None = None,
        *,
        flight_id: int | None = None,
        source: str = "mission.runtime",
    ) -> FlightEventEnvelopeV1 | MissionLifecycleEnvelopeV1:
        if event_type == "mission_state_changed":
            payload = (
                data
                if isinstance(data, MissionLifecyclePayloadV1)
                else MissionLifecyclePayloadV1.model_validate(data or {})
            )
            return await self.record_mission_lifecycle(
                payload,
                flight_id=flight_id,
                source=source,
            )
        return await self.record_flight_event(
            event_type,
            data=data,
            flight_id=flight_id,
            source=source,
        )
