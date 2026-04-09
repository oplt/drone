from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)  # also used as type in _aggregate_for_resolution

from backend.drone.models import Telemetry as TelemetryDTO

from ..models import (
    Flight,
    FlightEvent,
    FlightStatus,
    MavlinkEvent,
    TelemetryRecord,
    TelemetrySummary,
    normalize_flight_status,
)
from ..session import Session

if TYPE_CHECKING:
    from backend.runtime.envelopes import TelemetryEnvelopeV1

logger = logging.getLogger(__name__)
TERMINAL_FLIGHT_STATUSES = FlightStatus.terminal_values()


def _normalized_status_value(status: str | FlightStatus) -> str:
    return normalize_flight_status(status).value


def _status_is_terminal(status: str | FlightStatus) -> bool:
    try:
        return _normalized_status_value(status) in TERMINAL_FLIGHT_STATUSES
    except ValueError:
        return str(status).strip().lower() in TERMINAL_FLIGHT_STATUSES


class TelemetryRepository:
    def __init__(self, session_factory: type[Session] = Session):
        self._session_factory = session_factory

    # Backwards-compatible: save a loose telemetry row (no flight)
    async def save(self, t: TelemetryDTO) -> None:
        async with self._session_factory() as s:  # type: AsyncSession
            rec = TelemetryRecord(
                lat=t.lat,
                lon=t.lon,
                alt=t.alt,
                heading=t.heading,
                groundspeed=t.groundspeed,
                # armed=t.armed,
                mode=t.mode,
                battery_voltage=t.battery_voltage,
                battery_current=t.battery_current,
                battery_remaining=t.battery_remaining,
            )
            s.add(rec)
            await s.commit()

    # ---- New flight-aware methods ----

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
    ) -> int:
        normalized_status = _normalized_status_value(status)
        started_at = started_at or datetime.now(UTC)
        async with self._session_factory() as s:
            f = Flight(
                started_at=started_at,
                status=normalized_status,
                note=note,
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
                return len(payload)
            except Exception:
                await s.rollback()
                logger.exception("Failed batch insert of %d flight events", len(payload))
                return 0

    async def add_telemetry(self, flight_id: int, **fields) -> None:
        async with self._session_factory() as s:
            rec = TelemetryRecord(flight_id=flight_id, **fields)
            s.add(rec)
            await s.commit()

    # asyncpg caps bind parameters per statement at 32 767.
    # TelemetryRecord has ~12 columns → max ~2 700 rows per INSERT.
    # MavlinkEvent has 6 columns → max ~5 400 rows per INSERT.
    _PG_MAX_PARAMS = 32_767

    # ------- Faster bulk ingest APIs -------
    async def add_telemetry_many(self, flight_id: int, rows: Iterable[Mapping[str, Any]]) -> int:
        """Bulk insert telemetry. Each row is a dict of TelemetryRecord fields *excluding* id.
        Automatically chunks to stay within asyncpg's 32 767 bind-parameter limit.
        Returns total number of rows inserted.
        """
        payload = []
        for r in rows:
            d = dict(r)
            d.setdefault("flight_id", flight_id)
            payload.append(d)

        if not payload:
            return 0

        # Derive chunk size from the actual column count of the first row.
        chunk_size = max(1, self._PG_MAX_PARAMS // len(payload[0]))
        inserted = 0
        async with self._session_factory() as s:
            for start in range(0, len(payload), chunk_size):
                chunk = payload[start : start + chunk_size]
                await s.execute(insert(TelemetryRecord).values(chunk))
                inserted += len(chunk)
            await s.commit()
        return inserted

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
            return True

    async def get_telemetry_for_replay(
        self,
        flight_id: int,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10_000,
    ) -> Sequence[TelemetryRecord]:
        """
        Return typed TelemetryRecord rows for replay and dashboard use.

        Always reads from the `telemetry` table (typed scalar columns) — never
        from `mavlink_event` — so callers never scan the bulky JSON payload.
        Rows are ordered by created_at ASC, suitable for time-ordered replay.
        """
        async with self._session_factory() as s:
            stmt = (
                select(TelemetryRecord)
                .where(TelemetryRecord.flight_id == flight_id)
                .order_by(TelemetryRecord.created_at)
                .limit(limit)
            )
            if since is not None:
                stmt = stmt.where(TelemetryRecord.created_at >= since)
            if until is not None:
                stmt = stmt.where(TelemetryRecord.created_at <= until)
            result = await s.execute(stmt)
            return result.scalars().all()

    # repository.py
    async def add_mavlink_events_many(
        self, flight_id: int, rows: Iterable[Mapping[str, Any]]
    ) -> int:
        """
        rows dict keys expected:
          - msg_type (str)               -> defaults to payload['mavpackettype'] or 'UNKNOWN'
          - time_boot_ms (int|None)      -> stored as ms since boot
          - time_unix_usec (datetime|None)  # already converted in mqtt.py
          - timestamp (datetime|None)       # we'll also accept raw numeric and convert here
          - payload (dict)
          - flight_id is set here if missing
        """
        payload = []
        for r in rows:
            d = dict(r)
            d.setdefault("flight_id", flight_id)
            # derive msg_type if missing
            msg_type = d.get("msg_type") or d.get("payload", {}).get("mavpackettype") or "UNKNOWN"

            # Normalize time_boot_ms (ms since boot)
            time_boot_ms = d.get("time_boot_ms")
            if isinstance(time_boot_ms, (int, float)):
                try:
                    time_boot_ms = int(time_boot_ms)
                except Exception:
                    time_boot_ms = None
            else:
                time_boot_ms = None

            # normalize timestamp if someone passed numeric seconds
            ts = d.get("timestamp")
            if ts is not None and not isinstance(ts, datetime):
                try:
                    # handle int/float epoch seconds
                    ts = datetime.fromtimestamp(float(ts), tz=UTC)
                except Exception:
                    ts = datetime.now(UTC)
            elif ts is None:
                ts = datetime.now(UTC)

            payload.append(
                {
                    "flight_id": d["flight_id"],
                    "msg_type": msg_type,
                    "time_boot_ms": time_boot_ms,
                    "time_unix_usec": d.get("time_unix_usec"),
                    "timestamp": ts,
                    "payload": d.get("payload", {}),
                }
            )

        if not payload:
            return 0

        chunk_size = max(1, self._PG_MAX_PARAMS // len(payload[0]))
        inserted_total = 0
        async with self._session_factory() as s:
            for start in range(0, len(payload), chunk_size):
                chunk = payload[start : start + chunk_size]
                stmt = insert(MavlinkEvent).values(chunk)
                try:
                    await s.execute(stmt)
                    inserted_total += len(chunk)
                except Exception as e:
                    logger.error(f"Chunk insert failed for flight {flight_id} chunk@{start}: {e}")
                    await s.rollback()
                    for d in chunk:
                        try:
                            await s.execute(insert(MavlinkEvent).values(d))
                            inserted_total += 1
                        except Exception as single_e:
                            logger.error(f"Single insert failed for flight {flight_id}: {single_e}")
                            await s.rollback()
            await s.commit()
        logger.info(
            f"Successfully inserted {inserted_total} MavlinkEvent records for flight {flight_id}"
        )
        return inserted_total

    # ------------------------------------------------------------------
    # Downsampled summary aggregates
    # ------------------------------------------------------------------

    _VALID_RESOLUTIONS = frozenset({1, 10, 60})

    async def build_telemetry_summaries(self, flight_id: int) -> dict[int, int]:
        """
        Populate (or refresh) ``telemetry_summary`` for *flight_id* at all
        three resolutions (1 s, 10 s, 60 s).

        Old rows for this flight are deleted first so the method is idempotent.
        Returns ``{resolution_s: row_count}`` for logging.
        """
        counts: dict[int, int] = {}
        async with self._session_factory() as s:
            # Clear stale summaries for this flight.
            await s.execute(delete(TelemetrySummary).where(TelemetrySummary.flight_id == flight_id))
            await s.flush()

            for res_s in (1, 10, 60):
                rows = await self._aggregate_for_resolution(s, flight_id, res_s)
                if rows:
                    await s.execute(insert(TelemetrySummary).values(rows))
                counts[res_s] = len(rows)

            await s.commit()
        return counts

    @staticmethod
    async def _aggregate_for_resolution(
        session: AsyncSession,
        flight_id: int,
        res_s: int,
    ) -> list[dict[str, Any]]:
        """
        Group raw telemetry into ``res_s``-second buckets using epoch arithmetic.
        Returns a list of dicts ready for bulk insert into ``telemetry_summary``.
        """
        # Bucket expression: floor(epoch / res_s) * res_s → back to timestamp.
        epoch_expr = func.extract("epoch", TelemetryRecord.created_at)
        bucket_expr = func.to_timestamp(func.floor(epoch_expr / res_s) * res_s).label("bucket_ts")

        stmt = (
            select(
                bucket_expr,
                func.avg(TelemetryRecord.alt).label("avg_alt"),
                func.min(TelemetryRecord.alt).label("min_alt"),
                func.max(TelemetryRecord.alt).label("max_alt"),
                func.avg(TelemetryRecord.groundspeed).label("avg_groundspeed"),
                func.avg(TelemetryRecord.battery_remaining).label("avg_battery_remaining"),
                func.min(TelemetryRecord.battery_remaining).label("min_battery_remaining"),
                func.count().label("sample_count"),
            )
            .where(TelemetryRecord.flight_id == flight_id)
            .group_by(text("bucket_ts"))
            .order_by(text("bucket_ts"))
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        return [
            {
                "flight_id": flight_id,
                "resolution_s": res_s,
                "bucket_ts": row.bucket_ts,
                "avg_alt": row.avg_alt,
                "min_alt": row.min_alt,
                "max_alt": row.max_alt,
                "avg_groundspeed": row.avg_groundspeed,
                "avg_battery_remaining": row.avg_battery_remaining,
                "min_battery_remaining": row.min_battery_remaining,
                "sample_count": row.sample_count,
            }
            for row in rows
        ]

    async def get_telemetry_summary(
        self,
        flight_id: int,
        resolution_s: int,
    ) -> list[TelemetrySummary]:
        """
        Return pre-aggregated summary rows for ``flight_id`` at ``resolution_s``.
        ``resolution_s`` must be 1, 10, or 60.
        """
        if resolution_s not in self._VALID_RESOLUTIONS:
            raise ValueError(
                f"resolution_s must be one of {sorted(self._VALID_RESOLUTIONS)}, got {resolution_s}"
            )
        async with self._session_factory() as s:
            stmt = (
                select(TelemetrySummary)
                .where(
                    TelemetrySummary.flight_id == flight_id,
                    TelemetrySummary.resolution_s == resolution_s,
                )
                .order_by(TelemetrySummary.bucket_ts)
            )
            result = await s.execute(stmt)
            return list(result.scalars().all())


class TelemetryBatcher:
    """
    Bounded in-memory buffer that bulk-inserts TelemetryRecord rows.

    Rows are accumulated until either `max_size` rows are buffered *or*
    `flush_interval_s` seconds have elapsed since the last flush, whichever
    comes first.  Call `flush()` explicitly on shutdown to drain any remainder.

    Usage::

        batcher = TelemetryBatcher(repo, flight_id=42)
        await batcher.add(row_dict)   # called per telemetry envelope
        await batcher.flush()         # call once when the flight ends

    The class is also an async context manager — the buffer is flushed on exit::

        async with TelemetryBatcher(repo, flight_id=42) as batcher:
            await batcher.add(row_dict)
    """

    DEFAULT_MAX_SIZE: int = 200
    DEFAULT_FLUSH_INTERVAL_S: float = 5.0

    def __init__(
        self,
        repo: TelemetryRepository,
        flight_id: int,
        *,
        max_size: int = DEFAULT_MAX_SIZE,
        flush_interval_s: float = DEFAULT_FLUSH_INTERVAL_S,
    ) -> None:
        self._repo = repo
        self._flight_id = flight_id
        self._max_size = max_size
        self._flush_interval_s = flush_interval_s
        self._buffer: list[dict[str, Any]] = []
        self._last_flush_at: float = time.monotonic()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add(self, row: Mapping[str, Any]) -> None:
        """Buffer one row.  Flushes automatically when full or overdue."""
        async with self._lock:
            self._buffer.append(dict(row))
            if len(self._buffer) >= self._max_size or self._is_due():
                await self._do_flush()

    async def flush(self) -> int:
        """Drain the buffer immediately.  Returns the number of rows inserted."""
        async with self._lock:
            return await self._do_flush()

    # ------------------------------------------------------------------
    # Async context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> TelemetryBatcher:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.flush()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_due(self) -> bool:
        return (time.monotonic() - self._last_flush_at) >= self._flush_interval_s

    async def _do_flush(self) -> int:
        """Must be called with ``self._lock`` held."""
        if not self._buffer:
            return 0
        rows, self._buffer = self._buffer, []
        self._last_flush_at = time.monotonic()
        try:
            return await self._repo.add_telemetry_many(self._flight_id, rows)
        except Exception:
            logger.exception(
                "TelemetryBatcher flush failed for flight_id=%s (%d rows dropped)",
                self._flight_id,
                len(rows),
            )
            return 0

    # ------------------------------------------------------------------
    # Factory: build a TelemetryRecord row dict from a live envelope
    # ------------------------------------------------------------------

    @staticmethod
    def row_from_envelope(envelope: TelemetryEnvelopeV1) -> dict[str, Any] | None:
        """
        Convert a ``TelemetryEnvelopeV1`` to a dict suitable for
        ``add_telemetry_many``.  Returns ``None`` when the envelope lacks the
        minimum required fields (lat/lon/alt/mode).
        """
        p = envelope.payload
        lat = p.position.lat
        lon = p.position.lon
        alt = p.position.alt_m
        mode = p.flight_mode or ""

        if lat is None or lon is None or alt is None or not mode:
            return None

        return {
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "heading": p.motion.heading_deg or 0.0,
            "groundspeed": p.motion.groundspeed_mps or 0.0,
            "mode": mode[:32],
            "battery_voltage": p.battery.voltage_v,
            "battery_current": p.battery.current_a,
            "battery_remaining": p.battery.remaining_pct,
            "system_time": envelope.emitted_at,
        }
