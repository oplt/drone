from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from backend.modules.missions.flight_models import (
    FlightStatus,
    normalize_flight_status,
)

if TYPE_CHECKING:
    from backend.core.events.envelopes import TelemetryEnvelopeV1
    from backend.modules.telemetry.repository import TelemetryRepository

logger = logging.getLogger(__name__)
TERMINAL_FLIGHT_STATUSES = FlightStatus.terminal_values()


def _normalized_status_value(status: str | FlightStatus) -> str:
    return normalize_flight_status(status).value


def _status_is_terminal(status: str | FlightStatus) -> bool:
    try:
        return _normalized_status_value(status) in TERMINAL_FLIGHT_STATUSES
    except ValueError:
        return str(status).strip().lower() in TERMINAL_FLIGHT_STATUSES


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
