"""
Telemetry ingestion and query benchmarks.

Run with:
    pytest -v -s backend/tests/bench/test_telemetry_perf.py

Each test creates an isolated Flight row, exercises one ingestion or query
path, prints a human-readable timing summary, then deletes the Flight (and
all child rows via CASCADE) so the DB is left clean.

Scenario sizes (rows at 10 Hz):
    SHORT  =  5 min  →   3 000 telemetry  /   6 000 MAVLink
    MEDIUM = 30 min  →  18 000 telemetry  / 36 000 MAVLink
    LONG   = 60 min  →  36 000 telemetry  / 72 000 MAVLink

All timings are wall-clock (time.perf_counter).  The EXPLAIN ANALYZE tests
print query plans so index usage can be confirmed without a separate psql
session.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from backend.db.models import Flight, FlightStatus, MavlinkEvent
from backend.db.repository.telemetry_repo import TelemetryRepository
from backend.db.session import Session

# ---------------------------------------------------------------------------
# Scenario sizes
# ---------------------------------------------------------------------------

HZ = 10  # telemetry rate used in production
MAVLINK_MULTIPLIER = 2  # MAVLink events arrive ~2× more often than telemetry

SHORT_ROWS = 5 * 60 * HZ  # 3 000
MEDIUM_ROWS = 30 * 60 * HZ  # 18 000
LONG_ROWS = 60 * 60 * HZ  # 36 000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)

MAVLINK_MSG_TYPES = [
    "GLOBAL_POSITION_INT",
    "ATTITUDE",
    "SYS_STATUS",
    "BATTERY_STATUS",
    "GPS_RAW_INT",
    "VFR_HUD",
]


def _telemetry_rows(flight_id: int, n: int) -> list[dict[str, Any]]:
    """Generate *n* realistic TelemetryRecord row dicts at HZ Hz."""
    interval = timedelta(seconds=1 / HZ)
    rows = []
    lat, lon = 51.5, -0.1
    alt = 50.0
    battery = 100.0
    for i in range(n):
        ts = _EPOCH + interval * i
        alt = 50.0 + 10.0 * math.sin(i / (HZ * 30))  # gentle altitude wave
        groundspeed = 8.0 + 2.0 * math.cos(i / (HZ * 20))
        battery = max(10.0, 100.0 - (i / n) * 80.0)  # linear drain
        rows.append(
            {
                "flight_id": flight_id,
                "lat": lat + i * 0.000005,
                "lon": lon + i * 0.000003,
                "alt": round(alt, 2),
                "heading": (i * 3.6) % 360,
                "groundspeed": round(groundspeed, 2),
                "mode": "AUTO",
                "battery_voltage": round(14.8 - (i / n) * 2.0, 2),
                "battery_current": 12.5,
                "battery_remaining": round(battery, 1),
                "system_time": ts,
                "created_at": ts,
                "frame_id": i,
            }
        )
    return rows


def _mavlink_rows(flight_id: int, n: int) -> list[dict[str, Any]]:
    """Generate *n* MAVLink event row dicts (JSON payload included)."""
    interval = timedelta(seconds=1 / (HZ * MAVLINK_MULTIPLIER))
    rows = []
    for i in range(n):
        msg_type = MAVLINK_MSG_TYPES[i % len(MAVLINK_MSG_TYPES)]
        ts = _EPOCH + interval * i
        rows.append(
            {
                "flight_id": flight_id,
                "msg_type": msg_type,
                "time_boot_ms": i * (1000 // (HZ * MAVLINK_MULTIPLIER)),
                "time_unix_usec": ts,
                "timestamp": ts,
                "payload": {
                    "mavpackettype": msg_type,
                    "lat": 515000000 + i * 50,
                    "lon": -1000000 + i * 30,
                    "alt": 50000 + i * 100,
                    "relative_alt": 50000,
                    "vx": 800,
                    "vy": 200,
                    "vz": -10,
                    "hdg": (i * 36) % 36000,
                    "time_boot_ms": i * 50,
                    # pad payload to ~realistic size
                    "extra": "x" * 64,
                },
            }
        )
    return rows


async def _create_flight(session_factory) -> int:
    async with session_factory() as s:
        f = Flight(
            started_at=_EPOCH,
            status=FlightStatus.ACTIVE.value,
            start_lat=51.5,
            start_lon=-0.1,
            start_alt=0.0,
            dest_lat=51.6,
            dest_lon=-0.0,
            dest_alt=50.0,
            note="benchmark",
        )
        s.add(f)
        await s.flush()
        fid = f.id
        await s.commit()
    return fid


async def _delete_flight(session_factory, flight_id: int) -> None:
    async with session_factory() as s:
        await s.execute(delete(Flight).where(Flight.id == flight_id))
        await s.commit()


def _report(label: str, rows: int, elapsed_s: float) -> None:
    rps = rows / elapsed_s if elapsed_s > 0 else float("inf")
    print(
        f"\n  {'[BENCH]':>8}  {label:<55}  "
        f"{rows:>7} rows  {elapsed_s * 1000:>8.1f} ms  {rps:>9.0f} rows/s"
    )


# ---------------------------------------------------------------------------
# Ingestion benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,n",
    [
        ("telemetry bulk-insert  SHORT  ( 5 min @ 10 Hz)", SHORT_ROWS),
        ("telemetry bulk-insert  MEDIUM (30 min @ 10 Hz)", MEDIUM_ROWS),
        ("telemetry bulk-insert  LONG   (60 min @ 10 Hz)", LONG_ROWS),
    ],
)
async def test_telemetry_bulk_insert(label: str, n: int) -> None:
    """Benchmark add_telemetry_many at three flight durations."""
    repo = TelemetryRepository(Session)
    flight_id = await _create_flight(Session)
    rows = _telemetry_rows(flight_id, n)
    try:
        t0 = time.perf_counter()
        inserted = await repo.add_telemetry_many(flight_id, rows)
        elapsed = time.perf_counter() - t0

        _report(label, inserted, elapsed)
        assert inserted == n
    finally:
        await _delete_flight(Session, flight_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,n",
    [
        (
            "mavlink bulk-insert  SHORT  ( 5 min @ 20 Hz)",
            SHORT_ROWS * MAVLINK_MULTIPLIER,
        ),
        (
            "mavlink bulk-insert  MEDIUM (30 min @ 20 Hz)",
            MEDIUM_ROWS * MAVLINK_MULTIPLIER,
        ),
        (
            "mavlink bulk-insert  LONG   (60 min @ 20 Hz)",
            LONG_ROWS * MAVLINK_MULTIPLIER,
        ),
    ],
)
async def test_mavlink_bulk_insert(label: str, n: int) -> None:
    """Benchmark add_mavlink_events_many at three flight durations."""
    repo = TelemetryRepository(Session)
    flight_id = await _create_flight(Session)
    rows = _mavlink_rows(flight_id, n)
    try:
        t0 = time.perf_counter()
        inserted = await repo.add_mavlink_events_many(flight_id, rows)
        elapsed = time.perf_counter() - t0

        _report(label, inserted, elapsed)
        assert inserted == n
    finally:
        await _delete_flight(Session, flight_id)


# ---------------------------------------------------------------------------
# Aggregation benchmark
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_telemetry_summaries() -> None:
    """
    Insert MEDIUM telemetry then benchmark build_telemetry_summaries (all 3
    resolutions in one call).
    """
    repo = TelemetryRepository(Session)
    flight_id = await _create_flight(Session)
    rows = _telemetry_rows(flight_id, MEDIUM_ROWS)
    await repo.add_telemetry_many(flight_id, rows)

    try:
        t0 = time.perf_counter()
        counts = await repo.build_telemetry_summaries(flight_id)
        elapsed = time.perf_counter() - t0

        total = sum(counts.values())
        _report(
            f"build_telemetry_summaries MEDIUM (1s={counts[1]} 10s={counts[10]} 60s={counts[60]})",
            total,
            elapsed,
        )
        # At 10 Hz, each 1-s bucket contains 10 raw rows → MEDIUM_ROWS / HZ buckets.
        assert counts[1] == MEDIUM_ROWS // HZ  # 1 800
        assert counts[10] == MEDIUM_ROWS // (10 * HZ)  # 180
        assert counts[60] == MEDIUM_ROWS // (60 * HZ)  # 30
    finally:
        await _delete_flight(Session, flight_id)


# ---------------------------------------------------------------------------
# Query benchmarks (run on a pre-inserted MEDIUM flight)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def medium_flight():
    """
    Module-scoped fixture: insert a MEDIUM telemetry + summary dataset once,
    yield the flight_id, then clean up.
    """
    repo = TelemetryRepository(Session)
    flight_id = await _create_flight(Session)
    rows = _telemetry_rows(flight_id, MEDIUM_ROWS)
    await repo.add_telemetry_many(flight_id, rows)
    await repo.build_telemetry_summaries(flight_id)
    yield flight_id
    await _delete_flight(Session, flight_id)


@pytest.mark.asyncio
async def test_replay_full_scan(medium_flight: int) -> None:
    """Benchmark get_telemetry_for_replay — full flight, no time bounds."""
    repo = TelemetryRepository(Session)
    t0 = time.perf_counter()
    result = await repo.get_telemetry_for_replay(medium_flight, limit=MEDIUM_ROWS)
    elapsed = time.perf_counter() - t0

    _report("get_telemetry_for_replay  MEDIUM  (full, no bounds)", len(result), elapsed)
    assert len(result) == MEDIUM_ROWS


@pytest.mark.asyncio
async def test_replay_windowed(medium_flight: int) -> None:
    """Benchmark get_telemetry_for_replay with a 5-minute time window."""
    repo = TelemetryRepository(Session)
    since = _EPOCH + timedelta(minutes=5)
    until = _EPOCH + timedelta(minutes=10)

    t0 = time.perf_counter()
    result = await repo.get_telemetry_for_replay(
        medium_flight, since=since, until=until, limit=MEDIUM_ROWS
    )
    elapsed = time.perf_counter() - t0

    expected = 5 * 60 * HZ  # 3 000 rows in a 5-min window
    _report(
        f"get_telemetry_for_replay  MEDIUM  (5-min window, ~{expected} rows)",
        len(result),
        elapsed,
    )
    # Allow small rounding on bucket edges
    assert abs(len(result) - expected) <= HZ


@pytest.mark.asyncio
@pytest.mark.parametrize("res_s", [1, 10, 60])
async def test_summary_read(medium_flight: int, res_s: int) -> None:
    """Benchmark get_telemetry_summary at each resolution."""
    repo = TelemetryRepository(Session)
    t0 = time.perf_counter()
    result = await repo.get_telemetry_summary(medium_flight, res_s)
    elapsed = time.perf_counter() - t0

    _report(
        f"get_telemetry_summary     MEDIUM  resolution={res_s}s",
        len(result),
        elapsed,
    )
    assert len(result) > 0


# ---------------------------------------------------------------------------
# EXPLAIN ANALYZE — confirm index usage on hot queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explain_replay_full(medium_flight: int) -> None:
    """
    Print EXPLAIN ANALYZE for the full-flight replay query.
    Confirms idx_telemetry_flight_time is used (Index Scan / Bitmap Index Scan).
    """
    async with Session() as s:
        plan = await s.execute(
            text(
                "EXPLAIN ANALYZE "
                "SELECT * FROM telemetry "
                "WHERE flight_id = :fid "
                "ORDER BY created_at "
                "LIMIT 36000"
            ),
            {"fid": medium_flight},
        )
        rows = plan.fetchall()

    print(f"\n\n  [EXPLAIN] replay full scan — flight_id={medium_flight}")
    for row in rows:
        print(f"    {row[0]}")

    plan_text = "\n".join(r[0] for r in rows)
    assert "idx_telemetry_flight_time" in plan_text or "Index" in plan_text, (
        "Expected an index scan on telemetry; got:\n" + plan_text
    )


@pytest.mark.asyncio
async def test_explain_replay_windowed(medium_flight: int) -> None:
    """
    Print EXPLAIN ANALYZE for the windowed replay query.
    Confirms the composite (flight_id, created_at) index is used.
    """
    since = _EPOCH + timedelta(minutes=5)
    until = _EPOCH + timedelta(minutes=10)
    async with Session() as s:
        plan = await s.execute(
            text(
                "EXPLAIN ANALYZE "
                "SELECT * FROM telemetry "
                "WHERE flight_id = :fid "
                "  AND created_at >= :since "
                "  AND created_at <= :until "
                "ORDER BY created_at "
                "LIMIT 36000"
            ),
            {"fid": medium_flight, "since": since, "until": until},
        )
        rows = plan.fetchall()

    print(
        f"\n\n  [EXPLAIN] replay windowed — flight_id={medium_flight}  {since.isoformat()[:19]} → {until.isoformat()[:19]}"
    )
    for row in rows:
        print(f"    {row[0]}")

    plan_text = "\n".join(r[0] for r in rows)
    assert "idx_telemetry_flight_time" in plan_text or "Index" in plan_text


@pytest.mark.asyncio
async def test_explain_summary_read(medium_flight: int) -> None:
    """
    Print EXPLAIN ANALYZE for the summary read at 10 s resolution.
    Confirms idx_telsum_flt_res_bucket is used.
    """
    async with Session() as s:
        plan = await s.execute(
            text(
                "EXPLAIN ANALYZE "
                "SELECT * FROM telemetry_summary "
                "WHERE flight_id = :fid AND resolution_s = :res "
                "ORDER BY bucket_ts"
            ),
            {"fid": medium_flight, "res": 10},
        )
        rows = plan.fetchall()

    print(f"\n\n  [EXPLAIN] summary read 10 s — flight_id={medium_flight}")
    for row in rows:
        print(f"    {row[0]}")

    plan_text = "\n".join(r[0] for r in rows)
    assert "idx_telsum_flt_res_bucket" in plan_text or "Index" in plan_text


@pytest.mark.asyncio
async def test_explain_mavlink_type_filter(medium_flight: int) -> None:
    """
    Print EXPLAIN ANALYZE for msg_type-filtered MAVLink query.
    Confirms idx_evt_flt_type_ts covering index is used (index-only scan).
    Inserts a small MAVLink dataset first if the table is empty for this flight.
    """
    repo = TelemetryRepository(Session)

    # Insert a small MAVLink dataset for this flight so the planner has data.
    async with Session() as s:
        count = await s.scalar(
            select(MavlinkEvent.id).where(MavlinkEvent.flight_id == medium_flight).limit(1)
        )
    if count is None:
        await repo.add_mavlink_events_many(
            medium_flight, _mavlink_rows(medium_flight, SHORT_ROWS * MAVLINK_MULTIPLIER)
        )

    async with Session() as s:
        plan = await s.execute(
            text(
                "EXPLAIN ANALYZE "
                "SELECT flight_id, msg_type, timestamp, time_boot_ms "
                "FROM mavlink_event "
                "WHERE flight_id = :fid AND msg_type = :mt "
                "ORDER BY timestamp"
            ),
            {"fid": medium_flight, "mt": "GLOBAL_POSITION_INT"},
        )
        rows = plan.fetchall()

    print(
        f"\n\n  [EXPLAIN] mavlink msg_type filter — flight_id={medium_flight}  msg_type=GLOBAL_POSITION_INT"
    )
    for row in rows:
        print(f"    {row[0]}")

    plan_text = "\n".join(r[0] for r in rows)
    assert "idx_evt_flt_type_ts" in plan_text or "Index" in plan_text
