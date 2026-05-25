from __future__ import annotations

import logging

from backend.core.events import MissionLifecyclePayloadV1
from backend.modules.missions.flight_models import FlightStatus

logger = logging.getLogger(__name__)


class RuntimeCompletionServiceMixin:
    async def _finalize_started_flight(
        self,
        *,
        status: FlightStatus,
        note: str,
        event_type: str | None = None,
        event_data: dict | None = None,
    ) -> None:
        if self._flight_id is None:
            return

        safe_note = (note or "").strip()
        if len(safe_note) > 250:
            safe_note = safe_note[:247] + "..."

        if event_type:
            try:
                await self.record_flight_event(
                    event_type,
                    event_data or {},
                    flight_id=self._flight_id,
                    source="orchestrator.lifecycle",
                    category="mission",
                )
            except Exception:
                logger.exception(
                    "Failed to persist '%s' event for flight_id=%s", event_type, self._flight_id
                )

        lifecycle_state = {
            FlightStatus.ACTIVE: "running",
            FlightStatus.PAUSED: "paused",
            FlightStatus.INTERRUPTED: "aborted",
            FlightStatus.COMPLETED: "completed",
            FlightStatus.FAILED: "failed",
        }.get(status)
        if lifecycle_state is not None:
            try:
                await self.record_mission_lifecycle(
                    MissionLifecyclePayloadV1(
                        state=lifecycle_state,
                        trigger=event_type or "orchestrator.finalize",
                        reason=safe_note or None,
                        error=safe_note if status == FlightStatus.FAILED else None,
                    ),
                    flight_id=self._flight_id,
                    source="orchestrator.lifecycle",
                )
            except Exception:
                logger.exception(
                    "Failed to emit mission lifecycle for flight_id=%s status=%s",
                    self._flight_id,
                    status.value,
                )

        if self._telemetry_batcher is not None:
            try:
                await self._telemetry_batcher.flush()
            except Exception:
                logger.exception(
                    "TelemetryBatcher final flush failed for flight_id=%s", self._flight_id
                )
            finally:
                self._telemetry_batcher = None

        try:
            counts = await self._repo.build_telemetry_summaries(self._flight_id)
            logger.info("Telemetry summaries built for flight_id=%s: %s", self._flight_id, counts)
        except Exception:
            logger.exception("build_telemetry_summaries failed for flight_id=%s", self._flight_id)

        try:
            updated = await self.repo.finish_flight_if_in_progress(
                self._flight_id,
                status=status,
                note=safe_note,
            )
            if updated:
                logger.info("Marked flight_id=%s as %s", self._flight_id, status.value)
        except Exception:
            logger.exception(
                "Failed to update %s flight status for flight_id=%s",
                status.value,
                self._flight_id,
            )
