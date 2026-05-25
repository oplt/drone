from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RuntimePersistenceMixin:
    async def _shadow_write_event(self, flight_id: int, etype: str, data: dict[str, Any]) -> None:
        """Fire-and-forget coroutine that runs the OLD direct DB write path.

        Called only when shadow mode is active. Runs concurrently with the new
        queued path so both paths can be observed side-by-side without blocking
        the caller.  Any error here is logged and counted but never propagated.
        """
        self._metrics["shadow_writes_attempted"] += 1
        try:
            await self._repo.add_event(flight_id, etype, data)
            self._metrics["shadow_writes_ok"] += 1
        except Exception as exc:
            self._metrics["shadow_writes_failed"] += 1
            logger.warning(
                "Shadow write FAILED for event '%s' flight_id=%s: %s — "
                "new queued path will still persist this event.",
                etype,
                flight_id,
                exc,
            )

    def _maybe_schedule_shadow_write(
        self, flight_id: int, etype: str, data: dict[str, Any]
    ) -> None:
        """Schedule a shadow write only when shadow mode is enabled."""
        if not self._shadow_mode:
            return
        self._schedule_coro(self._shadow_write_event(flight_id, etype, data))

    def get_shadow_report(self) -> dict[str, Any]:
        """Return a summary comparing old vs new DB write paths under shadow mode."""
        attempted = self._metrics["shadow_writes_attempted"]
        ok = self._metrics["shadow_writes_ok"]
        failed = self._metrics["shadow_writes_failed"]
        new_enqueued = (
            self._metrics["flight_events_enqueued"] + self._metrics["lifecycle_events_enqueued"]
        )
        new_written = (
            self._metrics["db_event_worker_batches"]  # each batch may contain many rows
        )
        return {
            "shadow_mode_active": self._shadow_mode,
            "old_path": {
                "writes_attempted": attempted,
                "writes_ok": ok,
                "writes_failed": failed,
                "error_rate_pct": round(failed / attempted * 100, 2) if attempted else 0.0,
            },
            "new_path": {
                "events_enqueued": new_enqueued,
                "dropped_db_events": self._metrics["dropped_db_events"],
                "worker_batches_completed": new_written,
            },
            "interpretation": (
                "Both paths running. Compare error rates to validate new path stability."
                if self._shadow_mode
                else "Shadow mode disabled. Only new queued path is active."
            ),
        }

    async def _db_event_worker(self) -> None:
        """Drain _db_event_queue and batch-insert FlightEvent rows."""
        BATCH_SIZE = 200
        INTERVAL_S = 0.5
        buffer: list[tuple[int, str, dict]] = []

        logger.info("DB flight-event worker started")
        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(self._db_event_queue.get(), timeout=INTERVAL_S)
                    buffer.append(item)
                    while len(buffer) < BATCH_SIZE:
                        try:
                            buffer.append(self._db_event_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                    await self._repo.add_flight_events_many(buffer)
                    self._metrics["db_event_worker_batches"] += 1
                    buffer.clear()
                except TimeoutError:
                    if buffer:
                        await self._repo.add_flight_events_many(buffer)
                        self._metrics["db_event_worker_batches"] += 1
                        buffer.clear()
                except Exception:
                    logger.exception(
                        "DB event worker error — batch may be lost (%d rows)",
                        len(buffer),
                    )
                    buffer.clear()
        except asyncio.CancelledError:
            # Best-effort flush on shutdown
            if buffer:
                try:
                    await self._repo.add_flight_events_many(buffer)
                except Exception:
                    logger.exception("DB event worker shutdown flush failed")
            raise

        logger.info("DB flight-event worker stopped")

    async def _db_lifecycle_worker(self) -> None:
        """Drain _db_lifecycle_queue and persist lifecycle/mission_state_changed rows."""
        logger.info("DB lifecycle-event worker started")
        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(self._db_lifecycle_queue.get(), timeout=1.0)
                    flight_id, etype, data = item
                    try:
                        await self._repo.add_flight_events_many([(flight_id, etype, data)])
                        self._metrics["db_lifecycle_worker_writes"] += 1
                    except Exception:
                        logger.exception("DB lifecycle worker: failed to persist event '%s'", etype)
                except TimeoutError:
                    pass
                except Exception:
                    logger.exception("DB lifecycle worker error")
        except asyncio.CancelledError:
            raise

        logger.info("DB lifecycle-event worker stopped")

    def start_background_workers(self) -> None:
        """Create background asyncio tasks for DB writer workers.
        Must be called from within a running event loop (e.g. FastAPI lifespan).
        """
        self._bg_workers = [
            asyncio.create_task(self._db_event_worker(), name="OrchestratorDbEventWorker"),
            asyncio.create_task(self._db_lifecycle_worker(), name="OrchestratorDbLifecycleWorker"),
        ]
        logger.info(
            "Orchestrator background DB workers started (%d tasks)",
            len(self._bg_workers),
        )

    async def stop_background_workers(self) -> None:
        """Cancel and await all background worker tasks."""
        for task in self._bg_workers:
            if not task.done():
                task.cancel()
        for task in self._bg_workers:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Background worker raised on shutdown: %s", task.get_name())
        self._bg_workers.clear()
        logger.info("Orchestrator background workers stopped")

    def get_runtime_metrics(self) -> dict[str, Any]:
        """Return a snapshot of live operational metrics."""
        return {
            **self._metrics,
            "db_event_queue_depth": self._db_event_queue.qsize(),
            "db_event_queue_capacity": self._db_event_queue.maxsize,
            "db_lifecycle_queue_depth": self._db_lifecycle_queue.qsize(),
            "db_lifecycle_queue_capacity": self._db_lifecycle_queue.maxsize,
            "raw_event_queue_depth": self._raw_event_queue.qsize(),
            "raw_event_queue_capacity": self._raw_event_queue.maxsize,
            "telemetry_stream_running": self._telemetry_stream_running,
            "shadow_mode_active": self._shadow_mode,
        }
