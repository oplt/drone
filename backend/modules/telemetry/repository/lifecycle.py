from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import insert, select

from backend.infrastructure.cache.redis import get_redis_client
from backend.modules.analytics.cache import invalidate_overview
from backend.modules.missions.flight_models import (
    Flight,
    FlightEvent,
    FlightStatus,
    normalize_flight_status,
)
from backend.modules.telemetry.models import (
    TelemetryRecord,
)
from backend.modules.vehicle_runtime.types import Telemetry as TelemetryDTO

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
TERMINAL_FLIGHT_STATUSES = FlightStatus.terminal_values()


def _normalized_status_value(status: str | FlightStatus) -> str:
    return normalize_flight_status(status).value


def _status_is_terminal(status: str | FlightStatus) -> bool:
    try:
        return _normalized_status_value(status) in TERMINAL_FLIGHT_STATUSES
    except ValueError:
        return str(status).strip().lower() in TERMINAL_FLIGHT_STATUSES


async def _invalidate_analytics(org_id: int | None) -> None:
    if org_id is None:
        return
    try:
        await invalidate_overview(get_redis_client(), org_id)
    except Exception:
        logger.debug("Analytics cache invalidation skipped", exc_info=True)


class TelemetryLifecycleMixin:
    async def save(self, t: TelemetryDTO) -> None:
        async with self._session_factory() as s:
            rec = TelemetryRecord(
                lat=t.lat,
                lon=t.lon,
                alt=t.alt,
                heading=t.heading,
                groundspeed=t.groundspeed,
                mode=t.mode,
                battery_voltage=t.battery_voltage,
                battery_current=t.battery_current,
                battery_remaining=t.battery_remaining,
            )
            s.add(rec)
            await s.commit()

    async def create_flight(
        self,
        *,
        started_at: datetime | None = None,
        start_lat: float,
        start_lon: float,
        start_alt: float,
        dest_lat: float,
        dest_lon: float,
        dest_alt: float,
        status: str | FlightStatus = FlightStatus.ACTIVE,
        note: str = "",
        org_id: int | None = None,
    ) -> int:
        normalized_status = _normalized_status_value(status)
        started_at = started_at or datetime.now(UTC)
        async with self._session_factory() as s:
            f = Flight(
                started_at=started_at,
                status=normalized_status,
                note=note,
                org_id=org_id,
                start_lat=start_lat,
                start_lon=start_lon,
                start_alt=start_alt,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                dest_alt=dest_alt,
            )
            s.add(f)
            await s.flush()  # populates f.id
            fid = f.id
            await s.commit()
            await _invalidate_analytics(org_id)
            return fid

    async def add_event(
        self,
        flight_id: int | None,
        etype: str,
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None = None,
    ) -> None:
        if flight_id is None:
            logger.warning("Skipping flight event '%s': flight_id is None", etype)
            return
        if isinstance(data, BaseModel):
            serialized_data: dict[str, Any] = data.model_dump(
                mode="json",
                exclude_none=True,
            )
        elif isinstance(data, Mapping):
            serialized_data = dict(data)
        else:
            serialized_data = {}
        async with self._session_factory() as s:
            try:
                e = FlightEvent(flight_id=flight_id, type=etype, data=serialized_data)
                s.add(e)
                await s.commit()
                org_id = await s.scalar(select(Flight.org_id).where(Flight.id == flight_id))
                await _invalidate_analytics(org_id)
            except Exception:
                await s.rollback()
                logger.exception(
                    "Failed to persist flight event '%s' for flight_id=%s",
                    etype,
                    flight_id,
                )

    async def add_flight_events_many(
        self,
        rows: Iterable[tuple[int, str, dict[str, Any]]],
    ) -> int:
        """Batch insert flight events. Each row is (flight_id, etype, data_dict).
        Rows with flight_id=None are silently skipped.
        """
        payload = [
            {"flight_id": fid, "type": etype, "data": data}
            for fid, etype, data in rows
            if fid is not None
        ]
        if not payload:
            return 0
        async with self._session_factory() as s:
            try:
                stmt = insert(FlightEvent).values(payload)
                await s.execute(stmt)
                await s.commit()
                flight_ids = {row[0] for row in payload}
                org_ids = set(
                    await s.scalars(select(Flight.org_id).where(Flight.id.in_(flight_ids)))
                )
                for org_id in org_ids:
                    await _invalidate_analytics(org_id)
                return len(payload)
            except Exception:
                await s.rollback()
                logger.exception("Failed batch insert of %d flight events", len(payload))
                return 0

    async def finish_flight(
        self, flight_id: int, *, status: str | FlightStatus, note: str = ""
    ) -> None:
        normalized_status = _normalized_status_value(status)
        async with self._session_factory() as s:
            q = await s.execute(select(Flight).where(Flight.id == flight_id))
            f = q.scalar_one()
            f.status = normalized_status
            f.note = note
            f.ended_at = datetime.now(UTC)
            await s.commit()
            await _invalidate_analytics(f.org_id)

    async def finish_flight_if_in_progress(
        self, flight_id: int, *, status: str | FlightStatus, note: str = ""
    ) -> bool:
        """
        Finish a flight only if it is still active and has no ended_at.
        Returns True when a row was updated, False when already finalized.
        """
        normalized_status = _normalized_status_value(status)
        async with self._session_factory() as s:
            q = await s.execute(select(Flight).where(Flight.id == flight_id))
            f = q.scalar_one()
            if f.ended_at is not None or _status_is_terminal(f.status):
                return False

            f.status = normalized_status
            f.note = note
            f.ended_at = datetime.now(UTC)
            await s.commit()
            await _invalidate_analytics(f.org_id)
            return True

    async def set_flight_status_if_active(
        self,
        flight_id: int,
        *,
        status: str | FlightStatus,
        note: str = "",
    ) -> bool:
        """
        Update lifecycle status for an active flight.
        Returns False if the flight has already ended or is terminal.
        """
        normalized_status = _normalized_status_value(status)
        async with self._session_factory() as s:
            q = await s.execute(select(Flight).where(Flight.id == flight_id))
            f = q.scalar_one()
            if f.ended_at is not None or _status_is_terminal(f.status):
                return False

            f.status = normalized_status
            if note:
                f.note = note
            if normalized_status in TERMINAL_FLIGHT_STATUSES:
                f.ended_at = datetime.now(UTC)
            await s.commit()
            await _invalidate_analytics(f.org_id)
            return True
