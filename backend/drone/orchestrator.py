from __future__ import annotations

import asyncio
import inspect
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from pydantic import BaseModel
from pymavlink import mavutil
from .models import Coordinate
from .drone_base import DroneClient, MissionAbortRequested
from backend.map.google_maps import GoogleMapsClient
from backend.video.stream import DroneVideoStream
from backend.analysis.llm import LLMAnalyzer
from backend.messaging.mqtt import MqttClient
# from backend.messaging.opcua import DroneOpcUaServer
from backend.db.models import FlightStatus
from backend.db.repository.telemetry_repo import TelemetryBatcher, TelemetryRepository
from backend.config import settings
from backend.analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult
from backend.utils.geo import haversine_km, coord_from_home
from backend.flight.preflight_check.preflight_orch import PreflightOrchestrator
from backend.flight.preflight_check.schemas import CheckStatus
from backend.runtime import (
    FlightEventEnvelopeV1,
    FlightEventPayloadV1,
    FlightEventSeverityV1,
    MissionContextV1,
    MissionLifecycleEnvelopeV1,
    MissionLifecyclePayloadV1,
    TelemetryEnvelopeV1,
    TelemetryPayloadV1,
    VideoHealthEnvelopeV1,
    VideoHealthPayloadV1,
    next_runtime_sequence,
    utc_now,
)
from backend.runtime.mavlink import (
    TELEMETRY_MAVLINK_TYPES,
    check_mavlink_connection,
    process_mavlink_message,
    raw_event_from_mavlink_message,
)

logger = logging.getLogger(__name__)


class _OrchestratorRepositoryAdapter:
    """Route event writes through orchestrator-owned fan-out while delegating everything else."""

    def __init__(self, repo: TelemetryRepository, orchestrator: "Orchestrator") -> None:
        self._repo = repo
        self._orchestrator = orchestrator

    async def add_event(
        self,
        flight_id: Optional[int],
        etype: str,
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None = None,
    ) -> None:
        await self._orchestrator.record_persisted_event(
            etype,
            data=data,
            flight_id=flight_id,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repo, name)


class Orchestrator:
    def __init__(
            self,
            drone: DroneClient,
            maps: GoogleMapsClient,
            analyzer: LLMAnalyzer,
            mqtt: MqttClient | None,
            # opcua: DroneOpcUaServer,
            video: DroneVideoStream | None,
            telemetry_repo: TelemetryRepository,
    ):
        self.drone = drone
        self.maps = maps
        self.analyzer = analyzer
        self.mqtt = mqtt
        # self.opcua = opcua
        self.video = video
        self._repo = telemetry_repo
        self.repo = _OrchestratorRepositoryAdapter(telemetry_repo, self)
        self.range_model = SimpleWhPerKmModel()
        self._running = True
        self._dest_coord: Coordinate | None = None
        # self._heartbeat_task = None
        self._telemetry_interval = settings.telem_log_interval_sec
        self._flight_id = None
        self._raw_event_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=2000)
        # Bounded queues that decouple DB writes from the fan-out hot path.
        # Flight events (high-freq): drop-oldest on overflow so the control path is never blocked.
        self._db_event_queue: asyncio.Queue[tuple[int, str, dict]] = asyncio.Queue(maxsize=500)
        # Mission lifecycle events (low-freq, critical): never drop — await put() with a
        # generous timeout and warn; lifecycle events are rare so queue pressure is unlikely.
        self._db_lifecycle_queue: asyncio.Queue[tuple[int, str, dict]] = asyncio.Queue(maxsize=200)
        # Metrics counters (monotonically increasing, safe to read from any coroutine).
        self._metrics: dict[str, Any] = {
            "telemetry_envelopes_total": 0,
            "flight_events_enqueued": 0,
            "lifecycle_events_enqueued": 0,
            "dropped_db_events": 0,
            "db_event_worker_batches": 0,
            "db_lifecycle_worker_writes": 0,
            "ingest_started_at": None,
            # Shadow-mode counters — only incremented when shadow mode is active.
            "shadow_writes_attempted": 0,
            "shadow_writes_ok": 0,
            "shadow_writes_failed": 0,
        }
        self._shadow_mode: bool = settings.orchestrator_shadow_mode
        self._bg_workers: list[asyncio.Task] = []
        self._video_health_interval = 5.0  # Check video health every 5 seconds
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._telemetry_stream_running = False
        self._telemetry_thread: threading.Thread | None = None
        self._telemetry_mav_conn: mavutil.mavlink_connection | None = None
        self._telemetry_conn_str = settings.drone_conn_mavproxy
        self._telemetry_broadcast_interval = 0.1
        self._last_telemetry_snapshot: dict[str, Any] = (
            TelemetryPayloadV1().to_legacy_snapshot(timestamp_s=0.0)
        )
        # Batcher for TelemetryRecord bulk inserts — created per flight.
        self._telemetry_batcher: "TelemetryBatcher | None" = None

    @property
    def flight_id(self):
        return self._flight_id

    def _runtime_db_flight_id(self) -> Optional[int]:
        try:
            return int(self._flight_id) if self._flight_id is not None else None
        except (TypeError, ValueError):
            return None

    def _mission_context(self) -> MissionContextV1 | None:
        context = MissionContextV1(
            mission_name=getattr(self, "current_mission_name", None),
            mission_type=getattr(self, "current_mission_type", None),
            mission_task_type=getattr(self, "current_mission_task_type", None),
            preflight_run_id=getattr(self, "current_preflight_run_id", None),
        )
        return context if any(context.model_dump().values()) else None

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._event_loop = loop

    def telemetry_running(self) -> bool:
        return self._telemetry_stream_running

    def _current_mission_runtime_id(self) -> str | None:
        return getattr(self, "current_client_flight_id", None)

    def _sequence(self, source: str) -> int:
        return next_runtime_sequence(self._current_mission_runtime_id(), source)

    @staticmethod
    def _serialize_event_data(
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None,
    ) -> dict[str, Any]:
        if isinstance(data, BaseModel):
            return data.model_dump(mode="json", exclude_none=True)
        if isinstance(data, Mapping):
            return dict(data)
        return {}

    def _schedule_coro(self, coro: Any) -> None:
        if self._event_loop is None:
            try:
                self._event_loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("No event loop bound for orchestrator runtime fan-out")
                return
        future = asyncio.run_coroutine_threadsafe(coro, self._event_loop)
        future.add_done_callback(
            lambda f: logger.error("Runtime fan-out failed: %s", f.exception())
            if f.exception()
            else None
        )

    def _enqueue_raw_event(self, item: dict[str, Any]) -> None:
        try:
            self._raw_event_queue.put_nowait(item)
        except asyncio.QueueFull:
            try:
                _ = self._raw_event_queue.get_nowait()
                self._raw_event_queue.task_done()
            except Exception:
                pass
            try:
                self._raw_event_queue.put_nowait(item)
            except Exception:
                logger.warning("Dropping raw MAVLink event after queue overflow")

    # ------------------------------------------------------------------
    # Bounded-queue helpers — overflow policy
    # ------------------------------------------------------------------

    def _enqueue_db_event(self, flight_id: int, etype: str, data: dict[str, Any]) -> None:
        """Enqueue a flight-event DB write. Drop-oldest on overflow (high-freq events)."""
        item = (flight_id, etype, data)
        try:
            self._db_event_queue.put_nowait(item)
            self._metrics["flight_events_enqueued"] += 1
        except asyncio.QueueFull:
            # Drop the oldest entry to make room, then retry once.
            try:
                self._db_event_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._db_event_queue.put_nowait(item)
                self._metrics["flight_events_enqueued"] += 1
            except asyncio.QueueFull:
                pass
            self._metrics["dropped_db_events"] += 1
            logger.warning(
                "DB event queue full — dropped oldest flight event (total drops: %d)",
                self._metrics["dropped_db_events"],
            )

    async def _enqueue_lifecycle_event(
        self, flight_id: int, etype: str, data: dict[str, Any]
    ) -> None:
        """Enqueue a lifecycle DB write. Never drop — warn and wait briefly if queue is full."""
        item = (flight_id, etype, data)
        try:
            self._db_lifecycle_queue.put_nowait(item)
            self._metrics["lifecycle_events_enqueued"] += 1
        except asyncio.QueueFull:
            logger.warning(
                "Lifecycle DB queue full (%d capacity) — mission lifecycle event "
                "will be delayed until worker drains the queue.",
                self._db_lifecycle_queue.maxsize,
            )
            await asyncio.wait_for(self._db_lifecycle_queue.put(item), timeout=5.0)
            self._metrics["lifecycle_events_enqueued"] += 1

    # ------------------------------------------------------------------
    # Shadow-mode helpers
    # ------------------------------------------------------------------

    async def _shadow_write_event(
        self, flight_id: int, etype: str, data: dict[str, Any]
    ) -> None:
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
        new_enqueued = self._metrics["flight_events_enqueued"] + self._metrics["lifecycle_events_enqueued"]
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

    # ------------------------------------------------------------------
    # Background DB-writer workers
    # ------------------------------------------------------------------

    async def _db_event_worker(self) -> None:
        """Drain _db_event_queue and batch-insert FlightEvent rows."""
        BATCH_SIZE = 200
        INTERVAL_S = 0.5
        buffer: list[tuple[int, str, dict]] = []

        logger.info("DB flight-event worker started")
        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(
                        self._db_event_queue.get(), timeout=INTERVAL_S
                    )
                    buffer.append(item)
                    while len(buffer) < BATCH_SIZE:
                        try:
                            buffer.append(self._db_event_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                    await self._repo.add_flight_events_many(buffer)
                    self._metrics["db_event_worker_batches"] += 1
                    buffer.clear()
                except asyncio.TimeoutError:
                    if buffer:
                        await self._repo.add_flight_events_many(buffer)
                        self._metrics["db_event_worker_batches"] += 1
                        buffer.clear()
                except Exception:
                    logger.exception("DB event worker error — batch may be lost (%d rows)", len(buffer))
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
                    item = await asyncio.wait_for(
                        self._db_lifecycle_queue.get(), timeout=1.0
                    )
                    flight_id, etype, data = item
                    try:
                        await self._repo.add_flight_events_many([(flight_id, etype, data)])
                        self._metrics["db_lifecycle_worker_writes"] += 1
                    except Exception:
                        logger.exception("DB lifecycle worker: failed to persist event '%s'", etype)
                except asyncio.TimeoutError:
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
        logger.info("Orchestrator background DB workers started (%d tasks)", len(self._bg_workers))

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

    async def _fanout_runtime_envelope(
        self,
        envelope: TelemetryEnvelopeV1
        | FlightEventEnvelopeV1
        | MissionLifecycleEnvelopeV1
        | VideoHealthEnvelopeV1,
    ) -> None:
        from backend.messaging.websocket import telemetry_manager

        if isinstance(envelope, TelemetryEnvelopeV1):
            self._metrics["telemetry_envelopes_total"] += 1
            await telemetry_manager.ingest_telemetry_envelope(envelope)
            if self.mqtt:
                self.mqtt.publish(
                    "drone/runtime/telemetry",
                    envelope.model_dump_jsonable(),
                    qos=1,
                )
            if self._telemetry_batcher is not None:
                row = TelemetryBatcher.row_from_envelope(envelope)
                if row is not None:
                    await self._telemetry_batcher.add(row)
            return

        if self.mqtt:
            self.mqtt.publish(
                f"drone/runtime/{envelope.kind}",
                envelope.model_dump_jsonable(),
                qos=1,
            )
        await telemetry_manager.broadcast(
            {
                "type": envelope.kind,
                "data": envelope.model_dump_jsonable(),
            }
        )

    async def record_flight_event(
        self,
        event_type: str,
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None = None,
        *,
        flight_id: int | None = None,
        source: str = "mission.runtime",
        category: str | None = None,
        severity: FlightEventSeverityV1 | None = None,
    ) -> FlightEventEnvelopeV1:
        persisted_data = self._serialize_event_data(data)
        target_flight_id = flight_id if flight_id is not None else self._flight_id

        if isinstance(data, FlightEventPayloadV1):
            payload = data
        else:
            payload = FlightEventPayloadV1(
                event_name=event_type,
                category=category,
                severity=severity,
                attributes=persisted_data,
            )

        envelope = FlightEventEnvelopeV1(
            mission_runtime_id=self._current_mission_runtime_id(),
            db_flight_id=target_flight_id,
            sequence=self._sequence(source),
            emitted_at=utc_now(),
            source=source,
            mission=self._mission_context(),
            payload=payload,
        )
        # Fan-out to websocket/MQTT first — never blocked by DB latency.
        await self._fanout_runtime_envelope(envelope)

        if target_flight_id is not None:
            # New path: enqueue DB write; drop-oldest on overflow.
            self._enqueue_db_event(target_flight_id, event_type, persisted_data)
            # Shadow path (only when ORCHESTRATOR_SHADOW_MODE=true): also run the
            # old direct write so both paths can be observed simultaneously.
            self._maybe_schedule_shadow_write(target_flight_id, event_type, persisted_data)

        return envelope

    async def record_mission_lifecycle(
        self,
        payload: MissionLifecyclePayloadV1 | dict[str, Any] | Mapping[str, Any],
        *,
        flight_id: int | None = None,
        source: str = "orchestrator.lifecycle",
    ) -> MissionLifecycleEnvelopeV1:
        lifecycle_payload = (
            payload
            if isinstance(payload, MissionLifecyclePayloadV1)
            else MissionLifecyclePayloadV1.model_validate(payload)
        )
        target_flight_id = flight_id if flight_id is not None else self._flight_id

        envelope = MissionLifecycleEnvelopeV1(
            mission_runtime_id=self._current_mission_runtime_id(),
            db_flight_id=target_flight_id,
            sequence=self._sequence(source),
            emitted_at=utc_now(),
            source=source,
            mission=self._mission_context(),
            payload=lifecycle_payload,
        )
        # Fan-out first — never blocked by DB.
        await self._fanout_runtime_envelope(envelope)

        # Lifecycle events are critical — never drop. Use the dedicated lifecycle
        # queue which blocks briefly if full rather than silently discarding.
        if target_flight_id is not None:
            serialized = self._serialize_event_data(lifecycle_payload)
            await self._enqueue_lifecycle_event(
                target_flight_id, "mission_state_changed", serialized
            )
            # Shadow path: also run old direct write for comparison when enabled.
            self._maybe_schedule_shadow_write(
                target_flight_id, "mission_state_changed", serialized
            )

        return envelope

    async def record_persisted_event(
        self,
        event_type: str,
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None = None,
        *,
        flight_id: int | None = None,
        source: str = "mission.runtime",
    ) -> FlightEventEnvelopeV1 | MissionLifecycleEnvelopeV1:
        if event_type == "mission_state_changed":
            payload = (
                data
                if isinstance(data, MissionLifecyclePayloadV1)
                else MissionLifecyclePayloadV1.model_validate(data or {})
            )
            return await self.record_mission_lifecycle(
                payload,
                flight_id=flight_id,
                source=source,
            )
        return await self.record_flight_event(
            event_type,
            data=data,
            flight_id=flight_id,
            source=source,
        )

    async def start_live_telemetry(
        self,
        mavlink_connection_str: str | None = None,
    ) -> bool:
        if self._telemetry_stream_running:
            return False

        if self._event_loop is None:
            self.bind_event_loop(asyncio.get_running_loop())

        conn_str = mavlink_connection_str or self._telemetry_conn_str
        if not conn_str:
            raise RuntimeError("No MAVLink connection string provided for telemetry")

        self._telemetry_conn_str = conn_str
        self._telemetry_stream_running = True
        self._metrics["ingest_started_at"] = utc_now().isoformat()
        from backend.messaging.websocket import telemetry_manager

        telemetry_manager.set_runtime_active(running=True, source_connected=False)
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_worker,
            args=(conn_str,),
            daemon=True,
            name="OrchestratorTelemetryWorker",
        )
        self._telemetry_thread.start()
        logger.info("Orchestrator live telemetry ingest started")
        return True

    async def stop_live_telemetry(self) -> bool:
        if not self._telemetry_stream_running:
            return False

        self._telemetry_stream_running = False
        thread = self._telemetry_thread
        if thread and thread.is_alive():
            await asyncio.to_thread(thread.join, 3.0)
        self._telemetry_thread = None
        self._telemetry_mav_conn = None
        from backend.messaging.websocket import telemetry_manager

        telemetry_manager.set_runtime_active(running=False, source_connected=False)
        logger.info("Orchestrator live telemetry ingest stopped")
        return True

    def _telemetry_worker(self, conn_str: str) -> None:
        from backend.messaging.websocket import telemetry_manager

        mav_conn = None
        message_buffer: list[dict[str, Any]] = []
        last_broadcast_time = time.time()
        last_heartbeat_time = time.time()

        try:
            logger.info("Connecting orchestrator telemetry ingest to MAVLink: %s", conn_str)
            mav_conn = mavutil.mavlink_connection(
                conn_str,
                autoreconnect=True,
                retries=3,
                source_system=255,
            )
            self._telemetry_mav_conn = mav_conn
            telemetry_manager.set_runtime_active(running=True, source_connected=True)

            heartbeat = mav_conn.wait_heartbeat(timeout=10)
            if not heartbeat:
                raise RuntimeError("MAVLink heartbeat timeout")

            try:
                mav_conn.mav.request_data_stream_send(
                    mav_conn.target_system,
                    mav_conn.target_component,
                    mavutil.mavlink.MAV_DATA_STREAM_ALL,
                    10,
                    1,
                )
            except Exception as exc:
                logger.warning("Could not request MAVLink data streams: %s", exc)

            while self._telemetry_stream_running:
                try:
                    now_s = time.time()
                    if now_s - last_heartbeat_time > 5:
                        if not mav_conn or not check_mavlink_connection(mav_conn):
                            logger.warning("Telemetry MAVLink connection lost, reconnecting")
                            if mav_conn:
                                mav_conn.close()
                            mav_conn = mavutil.mavlink_connection(
                                conn_str,
                                autoreconnect=True,
                                retries=3,
                                source_system=255,
                            )
                            self._telemetry_mav_conn = mav_conn
                            telemetry_manager.set_runtime_active(
                                running=True,
                                source_connected=True,
                            )
                        last_heartbeat_time = now_s

                    msg = mav_conn.recv_match(
                        blocking=False,
                        timeout=0.05,
                        type=TELEMETRY_MAVLINK_TYPES,
                    )
                    if msg:
                        msg_dict = msg.to_dict()
                        emitted_s = time.time()
                        if self.mqtt:
                            raw_payload = dict(msg_dict)
                            raw_payload["timestamp"] = emitted_s
                            self.mqtt.publish(settings.telemetry_topic, raw_payload, qos=1)

                        if self._running and self._flight_id is not None:
                            self._enqueue_raw_event(
                                raw_event_from_mavlink_message(
                                    msg_dict,
                                    flight_id=self._flight_id,
                                    timestamp_s=emitted_s,
                                )
                            )

                        telemetry_delta = process_mavlink_message(
                            msg_dict,
                            current_snapshot=self._last_telemetry_snapshot,
                        )
                        if telemetry_delta:
                            snapshot = dict(self._last_telemetry_snapshot)
                            snapshot.update(telemetry_delta)
                            snapshot["timestamp"] = emitted_s
                            self._last_telemetry_snapshot = snapshot
                            message_buffer.append(telemetry_delta)

                    now_s = time.time()
                    if (
                        now_s - last_broadcast_time >= self._telemetry_broadcast_interval
                        and message_buffer
                    ):
                        consolidated: dict[str, Any] = {}
                        for update in message_buffer:
                            consolidated.update(update)

                        emitted_s = float(self._last_telemetry_snapshot.get("timestamp") or now_s)
                        snapshot = dict(self._last_telemetry_snapshot)
                        snapshot.update(consolidated)
                        snapshot["timestamp"] = emitted_s
                        self._last_telemetry_snapshot = snapshot

                        envelope = TelemetryEnvelopeV1(
                            mission_runtime_id=self._current_mission_runtime_id(),
                            db_flight_id=self._runtime_db_flight_id(),
                            sequence=self._sequence("orchestrator.telemetry"),
                            emitted_at=datetime.fromtimestamp(emitted_s, tz=timezone.utc),
                            source="orchestrator.telemetry",
                            mission=self._mission_context(),
                            payload=TelemetryPayloadV1.from_legacy_snapshot(
                                snapshot,
                                coalesced_message_count=len(message_buffer),
                            ),
                        )
                        self._schedule_coro(self._fanout_runtime_envelope(envelope))
                        message_buffer.clear()
                        last_broadcast_time = now_s

                    time.sleep(0.001)
                except Exception as exc:
                    if self._telemetry_stream_running:
                        logger.error("Telemetry ingest worker error: %s", exc)
                    time.sleep(0.1)
        except Exception as exc:
            logger.error("Orchestrator telemetry ingest failed: %s", exc)
        finally:
            if mav_conn is not None:
                try:
                    mav_conn.close()
                except Exception:
                    pass
            self._telemetry_mav_conn = None
            self._telemetry_stream_running = False
            telemetry_manager.set_runtime_active(running=False, source_connected=False)
            logger.info("Orchestrator telemetry worker stopped")

    async def heartbeat_task(self):
        logger.info("Starting heartbeat task...")
        try:
            while self._running:
                if self.mqtt:
                    self.mqtt.publish(
                        "drone/heartbeat",
                        {"timestamp": time.time(), "status": "alive"},
                        qos=1,
                    )
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.warning(f"Heartbeat task error: {e}")

    def _init_video(self) -> None:
        """Initialize the video stream from settings. Called after drone connects."""
        if not settings.drone_video_enabled:
            logger.info("Drone video streaming disabled in configuration")
            return
        if settings.drone_video_use_gazebo:
            logger.info("Gazebo video mode enabled; stream will be handled by API on demand")
            return
        if self.video is not None:
            logger.debug("Video stream already initialized, skipping")
            return
        try:
            cam_source: Any = settings.drone_video_source
            try:
                cam_source = int(cam_source)
            except (ValueError, TypeError):
                pass
            self.video = DroneVideoStream(
                source=cam_source,
                width=settings.drone_video_width,
                height=settings.drone_video_height,
                fps=settings.drone_video_fps,
                open_timeout_s=settings.drone_video_timeout,
                probe_indices=5,
                fallback_file=settings.drone_video_fallback if settings.drone_video_fallback else None,
                fps_limit=None,
                enable_recording=settings.drone_video_save_stream,
                recording_path=settings.drone_video_save_path,
                recording_format="mp4",
            )
            logger.info("Drone video stream initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize drone video stream: %s", e)
            self.video = None

    async def video_health_monitor_task(self):
        """Monitor video stream health and publish status"""
        logger.info("Starting video health monitor task...")

        while self._running:
            try:
                if self.video:
                    # Get video connection status
                    status = dict(self.video.get_connection_status())
                    status.setdefault("stream_started", True)
                    status.setdefault("source", getattr(self.video, "source", None))
                    recording_full_path = getattr(self.video, "recording_full_path", None)
                    if callable(recording_full_path):
                        status.setdefault("recording_path", recording_full_path())
                    video_payload = VideoHealthPayloadV1.from_status(status)
                    video_envelope = VideoHealthEnvelopeV1(
                        mission_runtime_id=getattr(
                            self,
                            "current_client_flight_id",
                            None,
                        ),
                        db_flight_id=self._runtime_db_flight_id(),
                        sequence=next_runtime_sequence(
                            getattr(self, "current_client_flight_id", None),
                            "orchestrator.video",
                        ),
                        emitted_at=utc_now(),
                        source="orchestrator.video",
                        mission=self._mission_context(),
                        payload=video_payload,
                    )

                    # Publish video health status to MQTT
                    if self.mqtt:
                        self.mqtt.publish(
                            "drone/video/status",
                            video_payload.to_legacy_status_payload(
                                timestamp_s=video_envelope.emitted_at.timestamp(),
                            ),
                            qos=1,
                        )
                        self.mqtt.publish(
                            "drone/runtime/video_health",
                            video_envelope.model_dump_jsonable(),
                            qos=1,
                        )

                    # Update OPC UA with video status
                    # await self.opcua.update_video_status(
                    #     healthy=status["healthy"],
                    #     fps=status["fps"],
                    #     recording=status["recording"],
                    # )

                    # Log warnings if video is unhealthy
                    if not video_payload.healthy:
                        logging.warning("Video stream is unhealthy")
                        if self.mqtt:
                            self.mqtt.publish(
                                "drone/warnings",
                                {
                                    "type": "video_stream_unhealthy",
                                    "message": "Video stream connection issues detected",
                                    "timestamp": time.time(),
                                },
                                qos=1,
                            )

                await asyncio.sleep(self._video_health_interval)

            except Exception as e:
                logger.error(f"Error in video health monitor: {e}")
                await asyncio.sleep(1.0)

    async def video_frame_pump_task(self):
        """Drain frames so the configured recorder actually receives video data."""
        if self.video is None:
            return

        logger.info("Starting video frame pump task...")
        frame_iter = self.video.frames()
        while self._running:
            try:
                packet = await asyncio.to_thread(next, frame_iter, None)
            except Exception as e:
                logger.error(f"Error in video frame pump: {e}")
                break

            if packet is None:
                break

            await asyncio.sleep(0)

    async def _raw_event_ingest_worker(self):
        BATCH_SIZE = 1000
        INTERVAL_S = 0.25
        buffer = []
        logger.info("Starting _raw_event_ingest_worker")

        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(
                        self._raw_event_queue.get(), timeout=INTERVAL_S
                    )
                    buffer.append(item)

                    # drain quickly
                    while len(buffer) < BATCH_SIZE:
                        try:
                            buffer.append(self._raw_event_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                    if self._flight_id is None:
                        buffer.clear()
                        continue

                    if buffer:
                        await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        # Only call task_done if you rely on queue.join()
                        for _ in range(len(buffer)):
                            self._raw_event_queue.task_done()
                        buffer.clear()

                except asyncio.TimeoutError:
                    if buffer and self._flight_id is not None:
                        await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        for _ in range(len(buffer)):
                            self._raw_event_queue.task_done()
                        buffer.clear()

        except asyncio.CancelledError:
            # graceful exit: best effort flush
            if buffer and self._flight_id is not None:
                try:
                    await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                except Exception:
                    pass
            raise

    async def emergency_monitor_task(self):
        """Monitor for emergency conditions and handle them"""
        while self._running:
            try:
                # Only act if the drone explicitly flagged an emergency trigger.
                if getattr(self.drone, "dead_mans_switch_triggered", False):
                    if self.mqtt:
                        self.mqtt.publish(
                            "drone/emergency",
                            {
                                "type": "dead_mans_switch_triggered",
                                "message": "Connection lost - drone executing emergency protocol",
                                "timestamp": time.time(),
                            },
                            qos=2,
                        )  # QoS 2 for critical emergency messages

                    # Stop all other operations
                    self._running = False
                    # Reset to avoid repeated notifications
                    try:
                        self.drone.dead_mans_switch_triggered = False
                    except Exception:
                        pass
                    break
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.info(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)


    async def _run_preflight_checks(
            self,
            waypoints: list[Coordinate],
            alt: float,
            *,
            raise_on_fail: bool = True,
            mission_data: dict | None = None,
            **kwargs,
    ):

        mission_data = mission_data or {
            "type": "route",
            "waypoints": [
                {"lat": w.lat, "lon": w.lon, "alt": getattr(w, "alt", None) or alt}
                for w in waypoints
            ],
            "speed": kwargs.pop("mission_speed", settings.cruise_speed_mps),
            "altitude_agl": alt,
        }

        vehicle_state = await asyncio.to_thread(self.drone.get_telemetry)
        orchestrator = PreflightOrchestrator(config=kwargs.pop("preflight_config", {}))
        config_overrides = dict(kwargs.pop("config_overrides", {}) or {})
        runtime_preflight = {
            "ENFORCE_PREFLIGHT_RANGE": settings.enforce_preflight_range,
            "HDOP_MAX": settings.HDOP_MAX,
            "SAT_MIN": settings.SAT_MIN,
            "HOME_MAX_DIST": settings.HOME_MAX_DIST,
            "GPS_FIX_TYPE_MIN": settings.GPS_FIX_TYPE_MIN,
            "EKF_THRESHOLD": settings.EKF_THRESHOLD,
            "COMPASS_HEALTH_REQUIRED": settings.COMPASS_HEALTH_REQUIRED,
            "BATTERY_MIN_V": settings.BATTERY_MIN_V,
            "BATTERY_MIN_PERCENT": settings.BATTERY_MIN_PERCENT,
            # Legacy aliases still used by some checks.
            "BATTERY_RESERVE_PCT": settings.BATTERY_MIN_PERCENT,
            "HEARTBEAT_MAX_AGE": settings.HEARTBEAT_MAX_AGE,
            "MSG_RATE_MIN_HZ": settings.MSG_RATE_MIN_HZ,
            "RTL_MIN_ALT": settings.RTL_MIN_ALT,
            "MIN_CLEARANCE": settings.MIN_CLEARANCE,
            "MIN_CLEARANCE_M": settings.MIN_CLEARANCE,
            "AGL_MIN": settings.AGL_MIN,
            "AGL_MAX": settings.AGL_MAX,
            "MAX_RANGE_M": settings.MAX_RANGE_M,
            "MAX_WAYPOINTS": settings.MAX_WAYPOINTS,
            "NFZ_BUFFER_M": settings.NFZ_BUFFER_M,
            "A_LAT_MAX": settings.A_LAT_MAX,
            "BANK_MAX_DEG": settings.BANK_MAX_DEG,
            "TURN_PENALTY_S": settings.TURN_PENALTY_S,
            "WP_RADIUS_M": settings.WP_RADIUS_M,
        }
        for key, value in runtime_preflight.items():
            config_overrides.setdefault(key, value)

        report = await orchestrator.run(
            vehicle_state,
            mission_data,
            flight_id=str(self._flight_id),
            allowed_modes=["STANDBY", "GUIDED", "AUTO", "LOITER"],
            config_overrides=config_overrides,
            **kwargs,
        )

        # --- log every individual result ---
        logger.info(
            f"Preflight overall: {report.overall_status} | "
            f"pass={report.summary.get('passed', 0)} "
            f"warn={report.summary.get('warned', 0)} "
            f"fail={report.summary.get('failed', 0)}"
        )
        for result in report.base_checks + report.mission_checks:
            level = (
                logging.WARNING if result.status == CheckStatus.WARN
                else logging.ERROR if result.status == CheckStatus.FAIL
                else logging.DEBUG
            )
            logger.log(level, f"  [{result.status}] {result.name}: {result.message or ''}")

        # --- publish report to MQTT so the ground station sees it ---
        if self.mqtt:
            self.mqtt.publish(
                "drone/preflight",
                {
                    "timestamp": time.time(),
                    "overall": report.overall_status,
                    "summary": report.summary,
                    "critical_failures": (
                        [{"name": c.name, "message": c.message}
                         for c in report.critical_failures]
                        if report.critical_failures else []
                    ),
                },
                qos=1,
            )

        # --- persist to DB ---
        if self._flight_id is not None:
            await self.record_flight_event(
                "preflight_report",
                {
                    "overall": report.overall_status,
                    "summary": report.summary,
                    "critical_failures": (
                        [c.name for c in report.critical_failures]
                        if report.critical_failures else []
                    ),
                },
                flight_id=self._flight_id,
                source="orchestrator.preflight",
                category="preflight",
            )

        # --- abort on hard failure ---
        if report.overall_status == CheckStatus.FAIL:
            failed_names = (
                [c.name for c in report.critical_failures]
                if report.critical_failures
                else [r.name for r in report.base_checks + report.mission_checks
                      if r.status == CheckStatus.FAIL]
            )
            if raise_on_fail:
                raise RuntimeError(
                    f"Preflight FAILED - mission aborted. "
                    f"Failed checks: {', '.join(failed_names)}"
                )

        # WARN is non-fatal: mission continues but operator has been notified
        if report.overall_status == CheckStatus.WARN:
            logger.warning("Preflight passed with warnings - proceeding with caution")

        return report

    async def _resolve_flight_record_anchor(
            self,
            *,
            mission=None,
            waypoints: list[Coordinate],
            alt: float,
    ) -> tuple[Coordinate, Coordinate, str]:
        if mission is not None:
            anchor_fn = getattr(mission, "get_flight_record_anchor", None)
            if callable(anchor_fn):
                try:
                    anchor = anchor_fn(float(alt))
                    if (
                        isinstance(anchor, tuple)
                        and len(anchor) == 3
                        and isinstance(anchor[0], Coordinate)
                        and isinstance(anchor[1], Coordinate)
                    ):
                        return anchor
                except Exception:
                    logger.exception("Failed resolving mission-specific flight record anchor")

        if waypoints:
            return waypoints[0], waypoints[-1], "mission_waypoints"

        try:
            telemetry = await asyncio.to_thread(self.drone.get_telemetry)
        except Exception:
            logger.exception("Failed to read telemetry while resolving local-mission flight anchor")
            telemetry = None

        candidates: list[tuple[str, object, object, object]] = []
        if telemetry is not None:
            candidates.extend(
                [
                    (
                        "telemetry_position",
                        getattr(telemetry, "lat", None),
                        getattr(telemetry, "lon", None),
                        getattr(telemetry, "alt", None),
                    ),
                    (
                        "telemetry_home",
                        getattr(telemetry, "home_lat", None),
                        getattr(telemetry, "home_lon", None),
                        getattr(telemetry, "alt", None),
                    ),
                ]
            )

        home_location = getattr(self.drone, "home_location", None)
        if home_location is not None:
            candidates.append(
                (
                    "drone_home",
                    getattr(home_location, "lat", None),
                    getattr(home_location, "lon", None),
                    getattr(home_location, "alt", None),
                )
            )

        for source, lat, lon, anchor_alt in candidates:
            if lat is None or lon is None:
                continue
            try:
                start = Coordinate(
                    lat=float(lat),
                    lon=float(lon),
                    alt=float(anchor_alt) if anchor_alt is not None else float(alt),
                )
            except (TypeError, ValueError):
                continue
            return start, start, source

        logger.warning(
            "No GPS/home anchor available for local-frame mission; using placeholder flight coordinates."
        )
        placeholder = Coordinate(lat=0.0, lon=0.0, alt=float(alt))
        return placeholder, placeholder, "placeholder"


    async def run_mission(self, mission: "Mission", alt: float = 30.0, flight_fn=None):
        self._flight_id = None
        self._running = True
        tasks: list[asyncio.Task] = []
        shared_runtime_recording_active = False
        telemetry_started_for_mission = False
        waypoints = mission.get_waypoints()
        cruise_alt = alt

        async def _finalize_started_flight(
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
                        "Failed to persist '%s' event for flight_id=%s",
                        event_type,
                        self._flight_id,
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

            # Drain any buffered telemetry rows before closing the flight record.
            if self._telemetry_batcher is not None:
                try:
                    await self._telemetry_batcher.flush()
                except Exception:
                    logger.exception(
                        "TelemetryBatcher final flush failed for flight_id=%s",
                        self._flight_id,
                    )
                finally:
                    self._telemetry_batcher = None

            # Build downsampled summary aggregates (1 s / 10 s / 60 s).
            try:
                counts = await self._repo.build_telemetry_summaries(self._flight_id)
                logger.info(
                    "Telemetry summaries built for flight_id=%s: %s",
                    self._flight_id,
                    counts,
                )
            except Exception:
                logger.exception(
                    "build_telemetry_summaries failed for flight_id=%s",
                    self._flight_id,
                )

            try:
                updated = await self.repo.finish_flight_if_in_progress(
                    self._flight_id,
                    status=status,
                    note=safe_note,
                )
                if updated:
                    logger.info(
                        "Marked flight_id=%s as %s",
                        self._flight_id,
                        status.value,
                    )
            except Exception:
                logger.exception(
                    "Failed to update %s flight status for flight_id=%s",
                    status.value,
                    self._flight_id,
                )

        try:
            # ------------------------------------------------------------------
            # STEP 1: Connect to drone
            # ------------------------------------------------------------------
            try:
                logger.info("🔌 Connecting to drone...")
                await asyncio.to_thread(self.drone.connect)
                logger.info("✅ Drone connected successfully")
                self._init_video()
            except Exception as e:  # FIX (Bug 2): bare except -> except Exception as e
                logger.exception(f"❌ Drone Connection failed: {e}")
                raise

            # ------------------------------------------------------------------
            # STEP 2: Create flight record
            # ------------------------------------------------------------------
            try:
                start, dest, anchor_source = await self._resolve_flight_record_anchor(
                    mission=mission,
                    waypoints=waypoints,
                    alt=alt,
                )
                self._flight_id = await self.repo.create_flight(
                    start_lat=start.lat,
                    start_lon=start.lon,
                    start_alt=alt,
                    dest_lat=dest.lat,
                    dest_lon=dest.lon,
                    dest_alt=alt,
                    status=FlightStatus.ACTIVE,
                )
                self._telemetry_batcher = TelemetryBatcher(
                    self._repo, self._flight_id
                )
                await self.record_flight_event(
                    "mission_created",
                    {
                        "alt": cruise_alt,
                        "waypoints": len(waypoints),
                        "flight_record_anchor": anchor_source,
                    },
                    flight_id=self._flight_id,
                    source="orchestrator.lifecycle",
                    category="mission",
                    severity=FlightEventSeverityV1.INFO,
                )
                await self.record_mission_lifecycle(
                    MissionLifecyclePayloadV1(
                        state="running",
                        trigger="orchestrator.start",
                    ),
                    flight_id=self._flight_id,
                    source="orchestrator.lifecycle",
                )
                await self.record_flight_event(
                    "connected",
                    {},
                    flight_id=self._flight_id,
                    source="orchestrator.lifecycle",
                    category="connection",
                    severity=FlightEventSeverityV1.INFO,
                )
                logger.info(f"✅ Created flight record with ID: {self._flight_id}")
            except Exception as e:  # FIX (Bug 2)
                logger.exception(f"❌ Flight record generation failed: {e}")
                raise

            # ------------------------------------------------------------------
            # STEP 3: Preflight checks
            # ------------------------------------------------------------------
            try:
                logger.info("🔍 Running preflight checks...")
                mission_data = mission.get_preflight_mission_data() if hasattr(mission, "get_preflight_mission_data") else None
                await self._run_preflight_checks(waypoints, alt, mission_data=mission_data)
                logger.info("✅ Preflight checks passed")
            except Exception as e:  # FIX (Bug 2)
                logger.exception(f"❌ Preflight checks failed: {e}")
                await _finalize_started_flight(
                    status=FlightStatus.INTERRUPTED,
                    note=f"Preflight blocked mission start: {e}",
                    event_type="mission_aborted",
                    event_data={"reason": str(e), "stage": "preflight"},
                )
                raise

            # ------------------------------------------------------------------
            # STEP 4: Start telemetry stream
            # ------------------------------------------------------------------
            try:
                logger.info("Starting orchestrator-owned telemetry ingest...")
                telemetry_started_for_mission = await self.start_live_telemetry(
                    settings.drone_conn_mavproxy
                )
                logger.info(
                    "✅ Telemetry ingest %s",
                    "started" if telemetry_started_for_mission else "already running",
                )
                await asyncio.sleep(1)
            except Exception as e:  # FIX (Bug 2)
                logger.warning(f"⚠️ Failed to start telemetry stream: {e}")
                await _finalize_started_flight(
                    status=FlightStatus.FAILED,
                    note=f"Telemetry startup failed: {e}",
                    event_type="mission_failed",
                    event_data={"error": str(e), "stage": "telemetry_start"},
                )
                raise

            # ------------------------------------------------------------------
            # STEP 5: Start video recording
            # ------------------------------------------------------------------
            if (
                settings.drone_video_use_gazebo
                and settings.drone_video_save_stream
                and getattr(mission, "mission_type", None) != "warehouse_scan"
            ):
                try:
                    from backend.video.runtime import shared_video_runtime

                    logger.info("Starting shared Gazebo video recording...")
                    recording_status = await shared_video_runtime.start_recording()
                    shared_runtime_recording_active = bool(recording_status.get("recording"))
                    if shared_runtime_recording_active:
                        logger.info(
                            "✅ Shared Gazebo video recording started: %s",
                            recording_status.get("recording_path"),
                        )
                        if self._flight_id is not None:
                            await self.record_flight_event(
                                "video_recording_started",
                                {
                                    "source": "shared_runtime",
                                    "recording_file": recording_status.get("recording_file"),
                                    "recording_path": recording_status.get("recording_path"),
                                },
                                flight_id=self._flight_id,
                                source="orchestrator.video",
                                category="video",
                            )
                    else:
                        logger.warning(
                            "Shared Gazebo video recording was requested but not started: %s",
                            recording_status.get("error") or "unknown error",
                        )
                except Exception as e:
                    logger.error(f"Failed to start shared Gazebo video recording: {e}")
            elif self.video and getattr(self.video, "enable_recording", False):
                try:
                    logger.info("Starting video recording...")
                    await asyncio.to_thread(self.video.start_recording)
                    logger.info("✅ Video recording started")
                except Exception as e:
                    logger.error(f"Failed to start video recording: {e}")

            # ------------------------------------------------------------------
            # STEP 6: Start background tasks and run flight.
            # ------------------------------------------------------------------
            try:
                tasks = [
                    asyncio.create_task(self.heartbeat_task()),
                    asyncio.create_task(self._raw_event_ingest_worker()),
                    asyncio.create_task(self.video_health_monitor_task()),
                    asyncio.create_task(self.emergency_monitor_task()),
                ]
                if self.video is not None and getattr(self.video, "enable_recording", False):
                    tasks.append(asyncio.create_task(self.video_frame_pump_task()))
                if flight_fn is not None:
                    flight_awaitable = flight_fn() if callable(flight_fn) else flight_fn
                    if not inspect.isawaitable(flight_awaitable):
                        raise TypeError(
                            "flight_fn must be an awaitable or a callable returning an awaitable."
                        )
                    await flight_awaitable
                    await _finalize_started_flight(
                        status=FlightStatus.COMPLETED,
                        note="Mission completed",
                        event_type="mission_completed",
                        event_data={},
                    )

            except MissionAbortRequested as e:
                logger.warning("🛑 Mission aborted by operator: %s", e)
                await _finalize_started_flight(
                    status=FlightStatus.INTERRUPTED,
                    note=f"Mission interrupted: {e}",
                    event_type="mission_aborted",
                    event_data={"reason": str(e)},
                )
                raise
            except Exception as e:
                logger.exception(f"❌ Mission failed: {e}")
                await _finalize_started_flight(
                    status=FlightStatus.FAILED,
                    note=f"Mission failed: {e}",
                    event_type="mission_failed",
                    event_data={"error": str(e)},
                )
                raise
        finally:
            # Graceful teardown — always runs after flight completes or fails.
            self._running = False

            pending_tasks = [t for t in tasks if not t.done()]
            for task in pending_tasks:
                task.cancel()

            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)

            if shared_runtime_recording_active:
                try:
                    from backend.video.runtime import shared_video_runtime

                    recording_status = await shared_video_runtime.stop_recording()
                    if self._flight_id is not None:
                        await self.record_flight_event(
                            "video_recording_stopped",
                            {
                                "source": "shared_runtime",
                                "recording_file": recording_status.get("recording_file"),
                                "recording_path": recording_status.get("recording_path"),
                            },
                            flight_id=self._flight_id,
                            source="orchestrator.video",
                            category="video",
                        )
                except Exception as e:
                    logger.warning(f"Failed to stop shared Gazebo video recording: {e}")

            if telemetry_started_for_mission:
                try:
                    await self.stop_live_telemetry()
                except Exception as e:
                    logger.warning(f"Failed to stop orchestrator telemetry ingest: {e}")

            try:
                await self._cleanup()
            except Exception as e:
                logger.warning(f"Failed during mission cleanup: {e}")


    async def _cleanup(self):
        """Clean up orchestrator resources"""
        try:
            self.drone.stop_dead_mans_switch()
        except Exception as e:
            logger.warning(f"Failed to stop dead man's switch: {e}")

        # if self.opcua:
        #     try:
        #         await self.opcua.stop()
        #     except Exception as e:
        #         logger.warning(f"Failed to stop OPC UA server: {e}")

        if self.video:
            try:
                self.video.close()
            except Exception as e:
                logger.warning(f"Failed to close video stream: {e}")

        try:
            self.drone.close()
        except Exception as e:
            logger.warning(f"Failed to close drone connection: {e}")
