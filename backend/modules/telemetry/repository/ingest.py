from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert

from backend.modules.missions.flight_models import (
    FlightStatus,
    normalize_flight_status,
)
from backend.modules.telemetry.models import (
    MavlinkEvent,
    TelemetryRecord,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
TERMINAL_FLIGHT_STATUSES = FlightStatus.terminal_values()
_MAVLINK_INSERT_SUMMARY: dict[int, tuple[int, float]] = {}
_MAVLINK_INSERT_SUMMARY_INTERVAL_S = 5.0


def _normalized_status_value(status: str | FlightStatus) -> str:
    return normalize_flight_status(status).value


def _status_is_terminal(status: str | FlightStatus) -> bool:
    try:
        return _normalized_status_value(status) in TERMINAL_FLIGHT_STATUSES
    except ValueError:
        return str(status).strip().lower() in TERMINAL_FLIGHT_STATUSES


class TelemetryIngestMixin:
    _PG_MAX_PARAMS = 32_767

    async def add_telemetry(self, flight_id: int, **fields) -> None:
        async with self._session_factory() as s:
            rec = TelemetryRecord(flight_id=flight_id, **fields)
            s.add(rec)
            await s.commit()

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
        _log_mavlink_insert_summary(flight_id, inserted_total)
        return inserted_total


def _log_mavlink_insert_summary(flight_id: int, inserted_total: int) -> None:
    now = time.monotonic()
    prior = _MAVLINK_INSERT_SUMMARY.get(flight_id)
    if prior is None:
        _MAVLINK_INSERT_SUMMARY[flight_id] = (inserted_total, now)
        return
    batch_total, last_logged_at = prior
    batch_total += inserted_total
    if now - last_logged_at < _MAVLINK_INSERT_SUMMARY_INTERVAL_S:
        _MAVLINK_INSERT_SUMMARY[flight_id] = (batch_total, last_logged_at)
        return
    logger.info(
        "MavlinkEvent batch persisted flight_id=%s inserted_events_count=%s flush_interval_ms=%s",
        flight_id,
        batch_total,
        int(_MAVLINK_INSERT_SUMMARY_INTERVAL_S * 1000),
    )
    _MAVLINK_INSERT_SUMMARY[flight_id] = (0, now)
