from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from pydantic import BaseModel

from backend.core.config.runtime import settings
from backend.core.events import MissionContextV1, TelemetryPayloadV1, next_runtime_sequence
from backend.modules.preflight.range_estimator import SimpleWhPerKmModel
from backend.modules.telemetry.repository import TelemetryBatcher, TelemetryRepository
from backend.modules.vehicle_runtime.types import Coordinate
from backend.modules.vehicle_runtime.vehicle_port import DroneClient

from .async_port import AsyncDronePort
from .ports import (
    MapPort,
    MessagePublisherPort,
    RuntimeFanoutPort,
    SharedVideoRuntimePort,
    TelemetryConnectionFactoryPort,
    VideoStreamFactoryPort,
    VideoStreamPort,
)

logger = logging.getLogger(__name__)


class _OrchestratorRepositoryAdapter:
    """Route event writes through runtime fan-out while delegating repository reads."""

    def __init__(self, repo: TelemetryRepository, orchestrator: Any) -> None:
        self._repo = repo
        self._orchestrator = orchestrator

    async def add_event(
        self,
        flight_id: int | None,
        etype: str,
        data: dict[str, Any] | Mapping[str, Any] | BaseModel | None = None,
    ) -> None:
        await self._orchestrator.record_persisted_event(etype, data=data, flight_id=flight_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repo, name)


class RuntimeCoordinationMixin:
    def __init__(
        self,
        drone: DroneClient,
        maps: MapPort,
        mqtt: MessagePublisherPort | None,
        video: VideoStreamPort | None,
        telemetry_repo: TelemetryRepository,
        *,
        fanout: RuntimeFanoutPort,
        telemetry_connections: TelemetryConnectionFactoryPort,
        video_factory: VideoStreamFactoryPort | None = None,
        shared_video: SharedVideoRuntimePort | None = None,
    ):
        self.drone = drone
        self.async_drone = AsyncDronePort(drone)
        self.maps = maps
        self.mqtt = mqtt
        self.video = video
        self.fanout = fanout
        self._telemetry_connections = telemetry_connections
        self._video_factory = video_factory
        self._shared_video = shared_video
        self._repo = telemetry_repo
        self.repo = _OrchestratorRepositoryAdapter(telemetry_repo, self)
        self.range_model = SimpleWhPerKmModel()
        self._running = True
        self._dest_coord: Coordinate | None = None
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
        self._telemetry_mav_conn: Any | None = None
        self._telemetry_conn_str = settings.drone_conn_mavproxy
        self._telemetry_broadcast_interval = 0.1
        self._last_telemetry_snapshot: dict[str, Any] = TelemetryPayloadV1().to_legacy_snapshot(
            timestamp_s=0.0
        )
        # Batcher for TelemetryRecord bulk inserts — created per flight.
        self._telemetry_batcher: TelemetryBatcher | None = None

    @property
    def flight_id(self):
        return self._flight_id

    def _runtime_db_flight_id(self) -> int | None:
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
            lambda f: (
                logger.error("Runtime fan-out failed: %s", f.exception()) if f.exception() else None
            )
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

    def _enqueue_db_event(self, flight_id: int, etype: str, data: dict[str, Any]) -> None:
        """Enqueue a flight-event DB write. Drop-oldest on overflow (high-freq events)."""
        item = (flight_id, etype, data)
        try:
            self._db_event_queue.put_nowait(item)
            self._metrics["flight_events_enqueued"] += 1
        except asyncio.QueueFull:
            # Drop the oldest entry to make room, then retry once.
            with suppress(asyncio.QueueEmpty):
                self._db_event_queue.get_nowait()
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
