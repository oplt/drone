"""Periodic background cleanup jobs for TTL-governed database records.

Three independent loops run as asyncio Tasks inside the lifespan:

  preflight_cleanup_loop
    Deletes expired ``PreflightRun`` rows (those whose ``expires_at`` is in
    the past).  Runs every ``PREFLIGHT_CLEANUP_INTERVAL_S`` seconds.
    TTL for new runs: ``PREFLIGHT_RUN_TTL_SECONDS`` (default 900 s).

  mission_cleanup_loop
    Deletes terminal ``MissionRuntime`` rows (and their ``OperatorCommand``
    audit records) whose ``ended_at`` is older than
    ``MISSION_RUNTIME_RETENTION_DAYS`` days.  Runs every
    ``MISSION_CLEANUP_INTERVAL_S`` seconds.

  telemetry_cleanup_loop
    Enforces independent retention windows for the three time-series tables
    so storage growth stays predictable:

      telemetry (raw)          TELEMETRY_RAW_RETENTION_DAYS        default 90 d
      telemetry_summary        TELEMETRY_SUMMARY_RETENTION_DAYS    default 365 d
      mavlink_event (raw)      MAVLINK_RETENTION_DAYS              default 14 d

    Raw MAVLink rows are purged most aggressively because the JSON payload
    column is the largest per-row cost and the data is rarely queried after
    a flight closes.  Raw telemetry is kept longer for replay.  Summaries
    are cheap (8 floats) and kept longest for dashboard trend queries.

    The loop runs every ``TELEMETRY_CLEANUP_INTERVAL_S`` seconds (default 6 h).
    Each sweep deletes in bounded batches (``TELEMETRY_CLEANUP_BATCH`` rows,
    default 10 000) to avoid long-running transactions on busy tables.

All environment variables are read once at module import so they appear in
startup logs alongside other config.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from backend.core.database.session import Session
from backend.core.logging.retention import cleanup_runtime_logs, runtime_log_retention_days
from backend.modules.missions.command_repository import operator_command_repo
from backend.modules.missions.repository import mission_runtime_repo
from backend.modules.preflight.repository import preflight_run_repo
from backend.modules.telemetry.models import MavlinkEvent, TelemetryRecord, TelemetrySummary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (env-overridable)
# ---------------------------------------------------------------------------

PREFLIGHT_CLEANUP_INTERVAL_S: int = max(60, int(os.getenv("PREFLIGHT_CLEANUP_INTERVAL_S", "300")))
"""How often to sweep for expired preflight runs (seconds, default 5 min)."""

MISSION_CLEANUP_INTERVAL_S: int = max(300, int(os.getenv("MISSION_CLEANUP_INTERVAL_S", "3600")))
"""How often to sweep for old terminal mission runtimes (seconds, default 1 h)."""

MISSION_RUNTIME_RETENTION_DAYS: int = max(1, int(os.getenv("MISSION_RUNTIME_RETENTION_DAYS", "30")))
"""Terminal mission runtimes older than this many days are deleted (default 30)."""

# -- Telemetry retention -------------------------------------------------------

TELEMETRY_CLEANUP_INTERVAL_S: int = max(
    3600, int(os.getenv("TELEMETRY_CLEANUP_INTERVAL_S", "21600"))
)
"""How often the telemetry retention sweep runs (seconds, default 6 h)."""

TELEMETRY_RAW_RETENTION_DAYS: int = max(1, int(os.getenv("TELEMETRY_RAW_RETENTION_DAYS", "90")))
"""Raw ``telemetry`` rows older than this many days are deleted (default 90 d)."""

TELEMETRY_SUMMARY_RETENTION_DAYS: int = max(
    1, int(os.getenv("TELEMETRY_SUMMARY_RETENTION_DAYS", "365"))
)
"""``telemetry_summary`` rows older than this many days are deleted (default 365 d)."""

MAVLINK_RETENTION_DAYS: int = max(1, int(os.getenv("MAVLINK_RETENTION_DAYS", "14")))
"""Raw ``mavlink_event`` rows older than this many days are deleted (default 14 d).

MAVLink rows carry large JSON payloads and are the most storage-expensive.
14 days is enough for post-flight debugging while keeping disk predictable.
"""

TELEMETRY_CLEANUP_BATCH: int = max(100, int(os.getenv("TELEMETRY_CLEANUP_BATCH", "10000")))
"""Maximum rows deleted per table per sweep (default 10 000).

Batching prevents long-held locks on high-volume tables and keeps each
DELETE transaction short enough to avoid WAL bloat.
"""

RUNTIME_LOG_CLEANUP_INTERVAL_S: int = max(
    3600, int(os.getenv("RUNTIME_LOG_CLEANUP_INTERVAL_S", "86400"))
)
"""How often runtime log retention cleanup runs (seconds, default 24 h)."""


# ---------------------------------------------------------------------------
# Cleanup coroutines
# ---------------------------------------------------------------------------


async def _preflight_cleanup_loop(stop_event: asyncio.Event) -> None:
    logger.info("preflight_cleanup_loop started (interval=%ds)", PREFLIGHT_CLEANUP_INTERVAL_S)
    while not stop_event.is_set():
        try:
            deleted = await preflight_run_repo.cleanup_expired()
            if deleted:
                logger.info("preflight_cleanup: deleted %d expired preflight run(s)", deleted)
        except Exception:
            logger.exception("preflight_cleanup: error during sweep")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=PREFLIGHT_CLEANUP_INTERVAL_S)
        except TimeoutError:
            pass  # Normal — interval elapsed, loop again.


async def _mission_cleanup_loop(stop_event: asyncio.Event) -> None:
    retention = timedelta(days=MISSION_RUNTIME_RETENTION_DAYS)
    logger.info(
        "mission_cleanup_loop started (interval=%ds, retention=%dd)",
        MISSION_CLEANUP_INTERVAL_S,
        MISSION_RUNTIME_RETENTION_DAYS,
    )
    while not stop_event.is_set():
        try:
            cutoff = datetime.now(UTC) - retention
            # Delete operator commands first (FK is SET NULL, but deleting
            # commands before runtimes avoids orphaned rows pointing to
            # NULL mission_runtime_id piling up indefinitely).
            cmd_deleted = await operator_command_repo.cleanup_old(older_than=cutoff)
            rt_deleted = await mission_runtime_repo.cleanup_terminal(older_than=cutoff)
            if cmd_deleted or rt_deleted:
                logger.info(
                    "mission_cleanup: deleted %d mission runtime(s) and %d command record(s) "
                    "older than %s",
                    rt_deleted,
                    cmd_deleted,
                    cutoff.strftime("%Y-%m-%d"),
                )
        except Exception:
            logger.exception("mission_cleanup: error during sweep")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=MISSION_CLEANUP_INTERVAL_S)
        except TimeoutError:
            pass


async def _delete_batch(
    session_factory: type,
    model: type,
    cutoff_col: object,
    cutoff: datetime,
    batch: int,
) -> int:
    """Delete up to ``batch`` rows of ``model`` older than ``cutoff``.

    Uses a subquery-based DELETE so the batch limit is respected on all
    PostgreSQL versions without relying on non-standard ``LIMIT`` in DELETE.
    Returns the number of rows actually deleted.
    """
    async with session_factory() as s:
        # Identify the oldest `batch` row PKs that exceed the cutoff.
        subq = (
            select(model.id)
            .where(cutoff_col < cutoff)
            .order_by(cutoff_col)
            .limit(batch)
            .scalar_subquery()
        )
        result = await s.execute(delete(model).where(model.id.in_(subq)))
        await s.commit()
        return result.rowcount


async def _telemetry_cleanup_loop(stop_event: asyncio.Event) -> None:
    raw_retention = timedelta(days=TELEMETRY_RAW_RETENTION_DAYS)
    summary_retention = timedelta(days=TELEMETRY_SUMMARY_RETENTION_DAYS)
    mavlink_retention = timedelta(days=MAVLINK_RETENTION_DAYS)

    logger.info(
        "telemetry_cleanup_loop started — interval=%ds  raw=%dd  summary=%dd  mavlink=%dd",
        TELEMETRY_CLEANUP_INTERVAL_S,
        TELEMETRY_RAW_RETENTION_DAYS,
        TELEMETRY_SUMMARY_RETENTION_DAYS,
        MAVLINK_RETENTION_DAYS,
    )

    while not stop_event.is_set():
        now = datetime.now(UTC)
        try:
            raw_cutoff = now - raw_retention
            raw_deleted = await _delete_batch(
                Session,
                TelemetryRecord,
                TelemetryRecord.created_at,
                raw_cutoff,
                TELEMETRY_CLEANUP_BATCH,
            )

            summary_cutoff = now - summary_retention
            summary_deleted = await _delete_batch(
                Session,
                TelemetrySummary,
                TelemetrySummary.bucket_ts,
                summary_cutoff,
                TELEMETRY_CLEANUP_BATCH,
            )

            mavlink_cutoff = now - mavlink_retention
            mavlink_deleted = await _delete_batch(
                Session,
                MavlinkEvent,
                MavlinkEvent.created_at,
                mavlink_cutoff,
                TELEMETRY_CLEANUP_BATCH,
            )

            if raw_deleted or summary_deleted or mavlink_deleted:
                logger.info(
                    "telemetry_cleanup: deleted raw=%d  summary=%d  mavlink=%d  "
                    "(cutoffs: raw<=%s  summary<=%s  mavlink<=%s)",
                    raw_deleted,
                    summary_deleted,
                    mavlink_deleted,
                    raw_cutoff.strftime("%Y-%m-%d"),
                    summary_cutoff.strftime("%Y-%m-%d"),
                    mavlink_cutoff.strftime("%Y-%m-%d"),
                )
        except Exception:
            logger.exception("telemetry_cleanup: error during sweep")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TELEMETRY_CLEANUP_INTERVAL_S)
        except TimeoutError:
            pass


async def _runtime_log_cleanup_loop(stop_event: asyncio.Event) -> None:
    retention_days = runtime_log_retention_days()
    logger.info(
        "runtime_log_cleanup_loop started (interval=%ds, retention=%dd)",
        RUNTIME_LOG_CLEANUP_INTERVAL_S,
        retention_days,
    )
    while not stop_event.is_set():
        try:
            deleted = await asyncio.to_thread(
                cleanup_runtime_logs,
                retention_days=retention_days,
            )
            if deleted:
                logger.info("runtime_log_cleanup: deleted %d expired log file(s)", deleted)
        except Exception:
            logger.exception("runtime_log_cleanup: error during sweep")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RUNTIME_LOG_CLEANUP_INTERVAL_S)
        except TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Lifecycle helpers — called from api_main.py lifespan
# ---------------------------------------------------------------------------

_stop_event: asyncio.Event | None = None
_tasks: list[asyncio.Task] = []


def start_cleanup_jobs() -> None:
    """Spawn cleanup loops as background asyncio Tasks."""
    global _stop_event, _tasks
    if _tasks:
        return  # Already started.
    _stop_event = asyncio.Event()
    _tasks = [
        asyncio.create_task(_preflight_cleanup_loop(_stop_event), name="preflight_cleanup"),
        asyncio.create_task(_mission_cleanup_loop(_stop_event), name="mission_cleanup"),
        asyncio.create_task(_telemetry_cleanup_loop(_stop_event), name="telemetry_cleanup"),
        asyncio.create_task(_runtime_log_cleanup_loop(_stop_event), name="runtime_log_cleanup"),
    ]
    logger.info("Cleanup jobs started (%d tasks)", len(_tasks))


async def stop_cleanup_jobs() -> None:
    """Signal cleanup loops to exit and wait for them to finish."""
    global _tasks
    if _stop_event is not None:
        _stop_event.set()
    for task in _tasks:
        try:
            await asyncio.wait_for(task, timeout=10.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
    _tasks = []
    logger.info("Cleanup jobs stopped")
