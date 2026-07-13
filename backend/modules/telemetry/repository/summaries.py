from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)  # also used as type in _aggregate_for_resolution

from backend.infrastructure.cache.redis import get_redis_client
from backend.modules.analytics.cache import invalidate_overview
from backend.modules.missions.flight_models import (
    Flight,
    FlightStatus,
    normalize_flight_status,
)
from backend.modules.telemetry.models import (
    TelemetryRecord,
    TelemetrySummary,
)

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


class TelemetrySummaryMixin:
    _VALID_RESOLUTIONS = frozenset({1, 10, 60})

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

            org_id = await s.scalar(
                select(Flight.org_id).where(Flight.id == flight_id)
            )
            await s.commit()
            if org_id is not None:
                try:
                    await invalidate_overview(get_redis_client(), org_id)
                except Exception:
                    logger.debug("Analytics cache invalidation skipped", exc_info=True)
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
