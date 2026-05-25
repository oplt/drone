from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from backend.core.config.runtime import settings
from backend.core.events import (
    FlightEventSeverityV1,
    MissionLifecyclePayloadV1,
)
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.telemetry.repository import TelemetryBatcher
from backend.modules.vehicle_runtime.types import Coordinate
from backend.modules.vehicle_runtime.vehicle_port import MissionAbortRequested

logger = logging.getLogger(__name__)


class RuntimeExecutionServiceMixin:
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
            "No GPS/home anchor available for local-frame mission; "
            "using placeholder flight coordinates."
        )
        placeholder = Coordinate(lat=0.0, lon=0.0, alt=float(alt))
        return placeholder, placeholder, "placeholder"

    async def run_mission(self, mission: Any, alt: float = 30.0, flight_fn=None):
        self._flight_id = None
        self._running = True
        tasks: list[asyncio.Task] = []
        shared_runtime_recording_active = False
        telemetry_started_for_mission = False
        waypoints = mission.get_waypoints()
        cruise_alt = alt

        try:
            # ------------------------------------------------------------------
            # STEP 1: Connect to drone
            # ------------------------------------------------------------------
            try:
                if getattr(self.drone, "vehicle", None):
                    logger.info("🔌 Drone already connected, skipping connect")
                else:
                    logger.info("🔌 Connecting to drone...")
                    await asyncio.to_thread(self.drone.connect)
                    logger.info("✅ Drone connected successfully")
                self._init_video()
            except Exception as e:
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
                self._telemetry_batcher = TelemetryBatcher(self._repo, self._flight_id)
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
                mission_data = (
                    mission.get_preflight_mission_data()
                    if hasattr(mission, "get_preflight_mission_data")
                    else None
                )
                await self._run_preflight_checks(waypoints, alt, mission_data=mission_data)
                logger.info("✅ Preflight checks passed")
            except Exception as e:  # FIX (Bug 2)
                logger.exception(f"❌ Preflight checks failed: {e}")
                await self._finalize_started_flight(
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
                await self._finalize_started_flight(
                    status=FlightStatus.FAILED,
                    note=f"Telemetry startup failed: {e}",
                    event_type="mission_failed",
                    event_data={"error": str(e), "stage": "telemetry_start"},
                )
                raise

            # ------------------------------------------------------------------
            # STEP 5: Start video recording
            # ------------------------------------------------------------------
            shared_runtime_recording_active = await self._start_mission_recording(mission)

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
                    await self._finalize_started_flight(
                        status=FlightStatus.COMPLETED,
                        note="Mission completed",
                        event_type="mission_completed",
                        event_data={},
                    )

            except MissionAbortRequested as e:
                logger.warning("🛑 Mission aborted by operator: %s", e)
                await self._finalize_started_flight(
                    status=FlightStatus.INTERRUPTED,
                    note=f"Mission interrupted: {e}",
                    event_type="mission_aborted",
                    event_data={"reason": str(e)},
                )
                raise
            except Exception as e:
                logger.exception(f"❌ Mission failed: {e}")
                await self._finalize_started_flight(
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

            await self._stop_mission_recording(shared_runtime_recording_active)

            if telemetry_started_for_mission:
                try:
                    await self.stop_live_telemetry()
                except Exception as e:
                    logger.warning(f"Failed to stop orchestrator telemetry ingest: {e}")

            try:
                await self._cleanup()
            except Exception as e:
                logger.warning(f"Failed during mission cleanup: {e}")
