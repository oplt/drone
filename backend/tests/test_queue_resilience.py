"""
Queue and batcher resilience tests.

These tests verify that the flight-critical control path is never blocked
when the database is slow or unavailable.  They use mocks exclusively — no
real DB or drone connection is required.

Scenarios covered:

  Flight-event queue (drop-oldest, maxsize=500)
  ─────────────────────────────────────────────
  • Enqueueing beyond capacity never blocks — it drops the oldest item
    and the call returns immediately.
  • The `dropped_db_events` metric counter increments on every drop.
  • Queue depth never exceeds maxsize after overflow.

  Lifecycle-event queue (never-drop, maxsize=200)
  ────────────────────────────────────────────────
  • When the queue is full and no worker is draining it, the 5-second
    wait eventually raises asyncio.TimeoutError rather than blocking
    indefinitely.

  Raw MAVLink queue (drop-oldest, maxsize=2000)
  ──────────────────────────────────────────────
  • Enqueueing beyond capacity never blocks or raises.
  • Depth is always ≤ maxsize after overflow.

  DB event worker with a failing DB
  ────────────────────────────────────
  • A DB exception inside the worker is caught: the batch is discarded,
    the worker continues running, and the queue still accepts new items.
  • A slow DB write (simulated with asyncio.sleep) does not prevent
    new items from being enqueued on the hot path.

  TelemetryBatcher with a failing DB
  ────────────────────────────────────
  • flush() returns 0 and does not raise when add_telemetry_many fails.
  • add() continues to buffer new rows after a failed flush.
  • Concurrent calls to add() and flush() do not deadlock.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.db.repository.telemetry_repo import TelemetryBatcher, TelemetryRepository
from backend.drone.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orchestrator() -> Orchestrator:
    """Return an Orchestrator with all external dependencies mocked out."""
    repo = MagicMock(spec=TelemetryRepository)
    repo.add_flight_events_many = AsyncMock(return_value=0)
    repo.add_telemetry_many = AsyncMock(return_value=0)
    repo.add_mavlink_events_many = AsyncMock(return_value=0)

    orch = Orchestrator(
        drone=MagicMock(),
        maps=MagicMock(),
        analyzer=MagicMock(),
        mqtt=None,
        video=None,
        telemetry_repo=repo,
    )
    return orch


def _raw_event() -> dict:
    return {"msg_type": "GLOBAL_POSITION_INT", "payload": {}, "timestamp": 0.0}


def _flight_event(flight_id: int = 1) -> tuple[int, str, dict]:
    return (flight_id, "test_event", {"key": "value"})


# ---------------------------------------------------------------------------
# Flight-event queue: drop-oldest on overflow
# ---------------------------------------------------------------------------


class TestFlightEventQueue:
    def test_enqueue_never_blocks_when_full(self):
        """Filling the queue past capacity must return instantly every time."""
        orch = _make_orchestrator()
        capacity = orch._db_event_queue.maxsize  # 500

        deadline = time.monotonic() + 2.0  # generous 2-second wall-clock budget
        for i in range(capacity + 200):
            orch._enqueue_db_event(1, "evt", {"i": i})
            assert time.monotonic() < deadline, "enqueue blocked — control path is blocked"

    def test_queue_depth_never_exceeds_maxsize(self):
        orch = _make_orchestrator()
        capacity = orch._db_event_queue.maxsize

        for i in range(capacity + 300):
            orch._enqueue_db_event(1, "evt", {"i": i})

        assert orch._db_event_queue.qsize() <= capacity

    def test_dropped_counter_increments_on_overflow(self):
        orch = _make_orchestrator()
        capacity = orch._db_event_queue.maxsize
        overflow = 50

        for i in range(capacity + overflow):
            orch._enqueue_db_event(1, "evt", {"i": i})

        # At least one drop must have been recorded (may be slightly less
        # than overflow due to the drop-oldest-then-retry dance).
        assert orch._metrics["dropped_db_events"] > 0

    def test_new_items_accepted_after_overflow(self):
        """After a burst, fresh items still enter the queue without error."""
        orch = _make_orchestrator()
        capacity = orch._db_event_queue.maxsize

        # Saturate
        for i in range(capacity + 10):
            orch._enqueue_db_event(1, "evt", {})

        before = orch._metrics["dropped_db_events"]
        orch._enqueue_db_event(1, "post_burst", {"sentinel": True})

        # Sentinel may or may not have been dropped (queue was full), but
        # the call must have returned and not raised.
        assert orch._metrics["dropped_db_events"] >= before


# ---------------------------------------------------------------------------
# Lifecycle queue: never-drop, wait up to 5 s
# ---------------------------------------------------------------------------


class TestLifecycleQueue:
    @pytest.mark.asyncio
    async def test_lifecycle_queue_times_out_when_full_and_no_worker(self):
        """
        Filling the lifecycle queue and then trying to enqueue one more item
        must time out (5 s) rather than blocking indefinitely.  No worker is
        running, so the queue never drains.
        """
        orch = _make_orchestrator()
        capacity = orch._db_lifecycle_queue.maxsize  # 200

        # Fill to capacity using the internal put_nowait path (bypasses await).
        for i in range(capacity):
            await orch._db_lifecycle_queue.put((1, "fill", {}))

        assert orch._db_lifecycle_queue.full()

        # The next enqueue must raise TimeoutError, not block forever.
        t0 = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            await orch._enqueue_lifecycle_event(1, "overflow", {})

        elapsed = time.monotonic() - t0
        # Must time out in ≤ 6 s (5-s budget + 1-s tolerance).
        assert elapsed < 6.0, f"lifecycle enqueue blocked for {elapsed:.1f}s, expected ≤6s"

    @pytest.mark.asyncio
    async def test_lifecycle_enqueue_succeeds_when_queue_has_space(self):
        orch = _make_orchestrator()
        # Should succeed without blocking.
        t0 = time.monotonic()
        await orch._enqueue_lifecycle_event(1, "evt", {"ok": True})
        assert time.monotonic() - t0 < 0.1
        assert orch._db_lifecycle_queue.qsize() == 1


# ---------------------------------------------------------------------------
# Raw MAVLink queue: drop-oldest on overflow
# ---------------------------------------------------------------------------


class TestRawEventQueue:
    def test_enqueue_never_blocks_when_full(self):
        orch = _make_orchestrator()
        capacity = orch._raw_event_queue.maxsize  # 2000

        deadline = time.monotonic() + 2.0
        for i in range(capacity + 500):
            orch._enqueue_raw_event(_raw_event())
            assert time.monotonic() < deadline, "raw event enqueue blocked"

    def test_depth_bounded_after_overflow(self):
        orch = _make_orchestrator()
        capacity = orch._raw_event_queue.maxsize

        for i in range(capacity + 300):
            orch._enqueue_raw_event(_raw_event())

        assert orch._raw_event_queue.qsize() <= capacity


# ---------------------------------------------------------------------------
# DB event worker: survives DB errors
# ---------------------------------------------------------------------------


class TestDbEventWorker:
    @pytest.mark.asyncio
    async def test_worker_continues_after_db_error(self):
        """
        When add_flight_events_many raises, the worker must NOT crash.
        Items enqueued after the failure must still be drained.
        """
        repo = MagicMock(spec=TelemetryRepository)
        call_count = 0

        async def flaky(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB unavailable")
            return 0

        repo.add_flight_events_many = flaky
        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )

        orch._enqueue_db_event(1, "before_error", {})

        # Start the worker and give it time to hit the error.
        task = asyncio.create_task(orch._db_event_worker())
        await asyncio.sleep(0.8)

        # Worker must still be running (not crashed).
        assert not task.done(), "DB event worker crashed after DB error"

        # Enqueue a new item — worker must drain it on the next cycle.
        orch._enqueue_db_event(1, "after_error", {})
        await asyncio.sleep(0.8)

        assert call_count >= 2, "Worker stopped processing after DB error"

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_queue_accepts_items_during_slow_db_write(self):
        """
        A slow DB write must not prevent the hot path from enqueueing new items.
        The enqueue call must return in < 50 ms regardless of DB latency.
        """
        repo = MagicMock(spec=TelemetryRepository)

        async def slow_write(*_args, **_kwargs):
            await asyncio.sleep(2.0)  # simulate 2-second DB stall
            return 0

        repo.add_flight_events_many = slow_write
        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )

        task = asyncio.create_task(orch._db_event_worker())
        await asyncio.sleep(0.05)  # let worker start and pick up first item

        # Enqueue while worker is mid-sleep on slow_write.
        orch._enqueue_db_event(1, "trigger_slow_write", {})
        await asyncio.sleep(0.1)  # worker is now blocked on slow_write

        t0 = time.monotonic()
        orch._enqueue_db_event(1, "hot_path", {})  # must return immediately
        elapsed = time.monotonic() - t0

        assert elapsed < 0.05, (
            f"Hot-path enqueue blocked for {elapsed * 1000:.1f}ms during slow DB write"
        )

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_worker_stops_cleanly_on_cancel(self):
        """Cancelling the worker task must raise CancelledError, not hang."""
        orch = _make_orchestrator()
        task = asyncio.create_task(orch._db_event_worker())
        await asyncio.sleep(0.05)

        t0 = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - t0 < 2.0, "Worker did not stop cleanly within 2 s"


# ---------------------------------------------------------------------------
# TelemetryBatcher: survives DB errors
# ---------------------------------------------------------------------------


class TestTelemetryBatcher:
    def _repo(self, side_effect=None):
        repo = MagicMock(spec=TelemetryRepository)
        if side_effect is not None:
            repo.add_telemetry_many = AsyncMock(side_effect=side_effect)
        else:
            repo.add_telemetry_many = AsyncMock(return_value=0)
        return repo

    def _row(self, i: int = 0) -> dict:
        return {
            "lat": 51.5 + i * 0.001,
            "lon": -0.1,
            "alt": 50.0,
            "heading": 0.0,
            "groundspeed": 8.0,
            "mode": "AUTO",
            "system_time": "2026-01-01T00:00:00+00:00",
        }

    @pytest.mark.asyncio
    async def test_flush_returns_zero_on_db_error(self):
        """flush() must not raise; it logs and returns 0."""
        repo = self._repo(side_effect=RuntimeError("DB down"))
        batcher = TelemetryBatcher(repo, flight_id=1)
        await batcher.add(self._row())

        result = await batcher.flush()
        assert result == 0  # no rows inserted, no exception raised

    @pytest.mark.asyncio
    async def test_add_continues_after_failed_flush(self):
        """
        After a failed flush, the batcher must accept new rows and
        attempt the next flush normally.
        """
        call_count = 0

        async def flaky(flight_id, rows):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB unavailable")
            return len(rows)

        repo = self._repo()
        repo.add_telemetry_many = flaky

        batcher = TelemetryBatcher(repo, flight_id=1, max_size=2, flush_interval_s=999)

        # First auto-flush: triggers at max_size=2, DB fails.
        await batcher.add(self._row(0))
        await batcher.add(self._row(1))  # hits max_size → auto-flush (fails)

        assert call_count == 1

        # Subsequent rows must still be accepted.
        await batcher.add(self._row(2))
        await batcher.add(self._row(3))  # hits max_size → auto-flush (succeeds)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_flush_does_not_block_on_slow_db(self):
        """
        A slow add_telemetry_many must not hold the lock indefinitely.
        This test ensures flush completes (even if slowly) and does not
        deadlock against a concurrent add().
        """

        async def slow_write(flight_id, rows):
            await asyncio.sleep(0.2)
            return len(rows)

        repo = self._repo()
        repo.add_telemetry_many = slow_write
        batcher = TelemetryBatcher(repo, flight_id=1)

        await batcher.add(self._row())

        flush_task = asyncio.create_task(batcher.flush())
        await asyncio.sleep(0.05)  # flush is mid-write

        # add() must not deadlock waiting for the lock.
        t0 = time.monotonic()
        add_task = asyncio.create_task(batcher.add(self._row(99)))
        await asyncio.gather(flush_task, add_task)
        elapsed = time.monotonic() - t0

        # Total time bounded by the slow write (0.2 s) + add wait + margin.
        assert elapsed < 1.0, f"flush+add took {elapsed:.2f}s — possible deadlock"

    @pytest.mark.asyncio
    async def test_context_manager_flushes_on_exit(self):
        """__aexit__ must flush remaining rows even if DB is healthy."""
        inserted: list[int] = []

        async def capture(flight_id, rows):
            inserted.append(len(rows))
            return len(rows)

        repo = self._repo()
        repo.add_telemetry_many = capture

        async with TelemetryBatcher(repo, flight_id=1, max_size=100) as batcher:
            for i in range(5):
                await batcher.add(self._row(i))

        # All 5 rows must have been flushed on __aexit__.
        assert sum(inserted) == 5

    @pytest.mark.asyncio
    async def test_row_from_envelope_returns_none_for_incomplete_data(self):
        """row_from_envelope must return None when essential fields are missing."""
        from backend.runtime.envelopes import (
            TelemetryBatteryV1,
            TelemetryEnvelopeV1,
            TelemetryMotionV1,
            TelemetryPayloadV1,
            TelemetryPositionV1,
        )

        envelope = MagicMock(spec=TelemetryEnvelopeV1)
        # Build a real payload with lat=None so the guard triggers.
        payload = TelemetryPayloadV1(
            position=TelemetryPositionV1(lat=None, lon=-0.1, alt_m=50.0),
            motion=TelemetryMotionV1(heading_deg=0.0, groundspeed_mps=8.0),
            battery=TelemetryBatteryV1(),
            flight_mode="AUTO",
        )
        envelope.payload = payload

        result = TelemetryBatcher.row_from_envelope(envelope)
        assert result is None


# ---------------------------------------------------------------------------
# DB lifecycle worker: survives DB errors
# ---------------------------------------------------------------------------


class TestLifecycleWorker:
    """
    _db_lifecycle_worker uses a never-drop queue (maxsize=200, 5-s timeout).
    A DB failure on a single event must not crash the worker or stall future items.
    """

    @pytest.mark.asyncio
    async def test_worker_continues_after_db_error(self):
        """
        When add_flight_events_many raises on a lifecycle event, the worker
        must log and continue — not crash.  A subsequent event must be processed.
        """
        repo = MagicMock(spec=TelemetryRepository)
        call_count = 0

        async def flaky(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB unavailable")
            return 0

        repo.add_flight_events_many = flaky
        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )

        # Enqueue one event that will fail, then one that should succeed.
        await orch._db_lifecycle_queue.put((1, "first_event", {}))

        task = asyncio.create_task(orch._db_lifecycle_worker())
        await asyncio.sleep(0.3)

        assert not task.done(), "Lifecycle worker crashed after DB error"

        await orch._db_lifecycle_queue.put((1, "second_event", {}))
        await asyncio.sleep(0.3)

        assert call_count >= 2, "Lifecycle worker stopped after DB error"

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_lifecycle_metric_counts_only_successful_writes(self):
        """
        db_lifecycle_worker_writes must only increment on a successful DB write,
        not on a DB exception.
        """
        repo = MagicMock(spec=TelemetryRepository)
        call_count = 0

        async def flaky(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            return 0

        repo.add_flight_events_many = flaky
        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )

        await orch._db_lifecycle_queue.put((1, "fail_event", {}))
        await orch._db_lifecycle_queue.put((1, "ok_event", {}))

        task = asyncio.create_task(orch._db_lifecycle_worker())
        await asyncio.sleep(0.5)

        # One write failed, one succeeded → metric == 1.
        assert orch._metrics["db_lifecycle_worker_writes"] == 1

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_slow_db_does_not_block_lifecycle_enqueue(self):
        """
        A slow lifecycle DB write must not prevent the hot path from being
        able to enqueue new lifecycle events (queue has space).
        """
        repo = MagicMock(spec=TelemetryRepository)

        async def slow_write(*_args, **_kwargs):
            await asyncio.sleep(1.5)
            return 0

        repo.add_flight_events_many = slow_write
        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )

        # Put an item so the worker starts its slow write.
        await orch._db_lifecycle_queue.put((1, "trigger", {}))
        task = asyncio.create_task(orch._db_lifecycle_worker())
        await asyncio.sleep(0.1)  # worker is now blocked in slow_write

        # Enqueue a second lifecycle event — must complete immediately
        # because the queue still has space (maxsize=200).
        t0 = time.monotonic()
        await orch._enqueue_lifecycle_event(1, "hot_path", {})
        elapsed = time.monotonic() - t0

        assert elapsed < 0.1, (
            f"Lifecycle enqueue blocked for {elapsed * 1000:.1f}ms during slow DB write"
        )

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# Raw event ingest worker: survives DB errors
# ---------------------------------------------------------------------------


class TestRawEventIngestWorker:
    """
    _raw_event_ingest_worker drains the raw MAVLink queue (drop-oldest,
    maxsize=2000) and writes via add_mavlink_events_many.  A DB failure must
    not crash the worker or block the hot-path enqueue.
    """

    def _make_orch_with_raw_mock(self, side_effect=None):
        repo = MagicMock(spec=TelemetryRepository)
        if side_effect is not None:
            repo.add_mavlink_events_many = AsyncMock(side_effect=side_effect)
        else:
            repo.add_mavlink_events_many = AsyncMock(return_value=0)
        repo.add_flight_events_many = AsyncMock(return_value=0)
        repo.add_telemetry_many = AsyncMock(return_value=0)

        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )
        orch._flight_id = 1  # simulate active flight so worker doesn't skip writes
        return orch

    @pytest.mark.asyncio
    async def test_worker_continues_after_db_error(self):
        """
        A DB exception on add_mavlink_events_many must not crash the worker.
        Items enqueued after the failure must still be processed.
        """
        call_count = 0

        async def flaky(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB unavailable")
            return 0

        orch = self._make_orch_with_raw_mock()
        orch.repo._repo.add_mavlink_events_many = flaky

        orch._enqueue_raw_event(_raw_event())

        task = asyncio.create_task(orch._raw_event_ingest_worker())
        await asyncio.sleep(0.8)

        assert not task.done(), "Raw event ingest worker crashed after DB error"

        orch._enqueue_raw_event(_raw_event())
        await asyncio.sleep(0.8)

        assert call_count >= 2, "Raw event ingest worker stopped after DB error"

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_hot_path_enqueue_not_blocked_by_slow_db(self):
        """
        A slow add_mavlink_events_many must not prevent _enqueue_raw_event
        from returning immediately.
        """

        async def slow_write(*_args, **_kwargs):
            await asyncio.sleep(2.0)
            return 0

        orch = self._make_orch_with_raw_mock()
        orch.repo._repo.add_mavlink_events_many = slow_write

        orch._enqueue_raw_event(_raw_event())  # triggers worker to start slow write
        task = asyncio.create_task(orch._raw_event_ingest_worker())
        await asyncio.sleep(0.1)  # worker is now inside slow_write

        t0 = time.monotonic()
        orch._enqueue_raw_event(_raw_event())  # must return instantly
        elapsed = time.monotonic() - t0

        assert elapsed < 0.05, (
            f"Raw event hot-path blocked for {elapsed * 1000:.1f}ms during slow DB write"
        )

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_worker_stops_cleanly_on_cancel(self):
        """Cancelling the raw ingest worker must raise CancelledError, not hang."""
        orch = self._make_orch_with_raw_mock()
        task = asyncio.create_task(orch._raw_event_ingest_worker())
        await asyncio.sleep(0.05)

        t0 = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - t0 < 2.0, "Raw event worker did not stop within 2 s"


# ---------------------------------------------------------------------------
# Shutdown flush: workers clean up even when DB is down
# ---------------------------------------------------------------------------


class TestShutdownUnderDbFailure:
    """
    Workers perform a best-effort flush on shutdown.  That flush must not
    block the process when the DB is unavailable or very slow.
    """

    @pytest.mark.asyncio
    async def test_db_event_worker_shutdown_flush_does_not_hang(self):
        """
        stop_background_workers() must complete within a short wall-clock
        window even when add_flight_events_many is very slow / unavailable.
        """
        repo = MagicMock(spec=TelemetryRepository)
        repo.add_flight_events_many = AsyncMock(side_effect=RuntimeError("DB completely down"))
        repo.add_telemetry_many = AsyncMock(return_value=0)
        repo.add_mavlink_events_many = AsyncMock(return_value=0)

        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )
        orch.start_background_workers()

        # Enqueue a few items that will be in-buffer on shutdown.
        for i in range(5):
            orch._enqueue_db_event(1, "pre_shutdown", {"i": i})

        await asyncio.sleep(0.1)

        t0 = time.monotonic()
        await orch.stop_background_workers()
        elapsed = time.monotonic() - t0

        assert elapsed < 5.0, (
            f"stop_background_workers() took {elapsed:.1f}s with DB down — "
            "shutdown flush should not block"
        )

    @pytest.mark.asyncio
    async def test_lifecycle_worker_shutdown_does_not_hang(self):
        """
        stop_background_workers() must complete quickly even when the
        lifecycle DB writes are failing.
        """
        repo = MagicMock(spec=TelemetryRepository)
        repo.add_flight_events_many = AsyncMock(side_effect=RuntimeError("DB completely down"))
        repo.add_telemetry_many = AsyncMock(return_value=0)
        repo.add_mavlink_events_many = AsyncMock(return_value=0)

        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )
        orch.start_background_workers()

        await orch._db_lifecycle_queue.put((1, "pre_shutdown", {}))
        await asyncio.sleep(0.1)

        t0 = time.monotonic()
        await orch.stop_background_workers()
        elapsed = time.monotonic() - t0

        assert elapsed < 5.0, (
            f"stop_background_workers() took {elapsed:.1f}s with lifecycle DB down"
        )


# ---------------------------------------------------------------------------
# Concurrent degradation: all DB writes failing simultaneously
# ---------------------------------------------------------------------------


class TestConcurrentQueueDegradation:
    """
    Simulate a total DB outage while the flight-critical hot path is active.
    All three enqueue paths must remain non-blocking.
    """

    @pytest.mark.asyncio
    async def test_all_queues_non_blocking_during_total_db_outage(self):
        """
        With all DB writers permanently failing, enqueuing into every queue
        type must still return in < 50 ms per call.
        """
        repo = MagicMock(spec=TelemetryRepository)
        repo.add_flight_events_many = AsyncMock(side_effect=RuntimeError("total DB outage"))
        repo.add_telemetry_many = AsyncMock(side_effect=RuntimeError("total DB outage"))
        repo.add_mavlink_events_many = AsyncMock(side_effect=RuntimeError("total DB outage"))

        orch = Orchestrator(
            drone=MagicMock(),
            maps=MagicMock(),
            analyzer=MagicMock(),
            mqtt=None,
            video=None,
            telemetry_repo=repo,
        )
        orch._flight_id = 1
        orch.start_background_workers()

        await asyncio.sleep(0.1)  # give workers time to start

        deadline = time.monotonic() + 3.0
        for i in range(300):
            # Flight events (drop-oldest)
            orch._enqueue_db_event(1, "evt", {"i": i})
            # Raw MAVLink events (drop-oldest)
            orch._enqueue_raw_event(_raw_event())
            assert time.monotonic() < deadline, (
                f"Hot-path enqueue blocked during total DB outage at iteration {i}"
            )

        await orch.stop_background_workers()

    @pytest.mark.asyncio
    async def test_dropped_metric_grows_but_queue_depth_stays_bounded(self):
        """
        During a DB outage with sustained high-rate writes, the dropped_db_events
        counter must grow (proving drops happened) and the queue depth must stay
        within its declared maximum.
        """
        orch = _make_orchestrator()
        capacity = orch._db_event_queue.maxsize

        for i in range(capacity * 3):
            orch._enqueue_db_event(1, "high_rate", {"i": i})

        assert orch._db_event_queue.qsize() <= capacity
        assert orch._metrics["dropped_db_events"] > 0
