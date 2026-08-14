from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.core.types.geo import coord_from_home
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.planning.event_response import generate_event_triggered_patrol_plan
from backend.modules.patrol.planning.geometry import (
    dynamic_trigger_profile,
)
from backend.modules.patrol.planning.grid import generate_grid_surveillance_plan
from backend.modules.patrol.planning.missions.event_triggered_flight import (
    EventTriggeredPatrolFlightMixin,
)
from backend.modules.patrol.planning.ml_binding import (
    build_zone_config,
    patrol_ml_runtime_payload,
    start_patrol_ml_runtime,
    stop_patrol_ml_runtime,
)
from backend.modules.patrol.planning.models import PrivatePatrolPlan
from backend.modules.patrol.planning.normalization import (
    normalize_ai_tasks,
)
from backend.modules.patrol.planning.types import PatrolResponseMode, PatrolTask
from backend.modules.patrol.vision.runtime import ml_runtime
from backend.modules.vehicle_runtime.orchestrator import Orchestrator
from backend.modules.vehicle_runtime.types import Coordinate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventTriggeredPatrolMission(EventTriggeredPatrolFlightMixin):
    trigger_id: str = ""
    sensor_id: str = ""
    response_mode: PatrolResponseMode = "incident_response"
    event_location_lonlat: tuple[float, float] | None = None
    geofence_polygon_lonlat: tuple[tuple[float, float], ...] = ()
    altitude_agl: float = 30.0
    speed_mps: float = 6.0
    verification_loiter_s: float = 45.0
    track_target: bool = True
    auto_stream_video: bool = True
    record_video_stream: bool = True
    verification_radius_m: float = 18.0
    target_label: str | None = None
    search_grid_spacing_m: float = 40.0
    search_grid_angle_deg: float = 0.0
    ai_tasks: tuple[PatrolTask, ...] = PATROL_AI_TASKS
    interpolate_steps: int = 6

    mission_type: str = "private_patrol_event_triggered"

    def __post_init__(self) -> None:
        if float(self.altitude_agl) <= 0:
            raise ValueError("altitude_agl must be > 0")
        if float(self.speed_mps) <= 0:
            raise ValueError("speed_mps must be > 0")
        if float(self.verification_loiter_s) < 0:
            raise ValueError("verification_loiter_s must be >= 0")
        if float(self.verification_radius_m) < 0:
            raise ValueError("verification_radius_m must be >= 0")
        if len(self.geofence_polygon_lonlat) < 3:
            raise ValueError("geofence_polygon_lonlat requires at least 3 points")
        if self.response_mode == "incident_response":
            if self.event_location_lonlat is None:
                raise ValueError("incident_response requires event_location_lonlat")
            lon = float(self.event_location_lonlat[0])
            lat = float(self.event_location_lonlat[1])
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                raise ValueError("event_location_lonlat must be valid [lon, lat]")
        object.__setattr__(self, "ai_tasks", normalize_ai_tasks(self.ai_tasks))

    def _make_incident_plan(self, *, altitude_agl: float) -> PrivatePatrolPlan:
        if self.event_location_lonlat is None:
            raise ValueError("incident_response requires event_location_lonlat")
        return generate_event_triggered_patrol_plan(
            self.event_location_lonlat,
            altitude_agl_m=float(altitude_agl),
            verification_radius_m=float(self.verification_radius_m),
            geofence_polygon_lonlat=self.geofence_polygon_lonlat,
        )

    def _make_search_plan(self, *, altitude_agl: float) -> PrivatePatrolPlan:
        return generate_grid_surveillance_plan(
            list(self.geofence_polygon_lonlat),
            altitude_agl_m=float(altitude_agl),
            grid_spacing_m=float(self.search_grid_spacing_m),
            grid_angle_deg=float(self.search_grid_angle_deg),
        )

    def _make_plan(self, *, altitude_agl: float | None = None) -> PrivatePatrolPlan:
        alt = float(self.altitude_agl if altitude_agl is None else altitude_agl)
        if self.response_mode == "detection_search":
            return self._make_search_plan(altitude_agl=alt)
        return self._make_incident_plan(altitude_agl=alt)

    def get_waypoints(self) -> list[Coordinate]:
        points = self._make_plan().waypoints
        if self.response_mode == "incident_response" and len(points) == 1:
            wp = points[0]
            return [wp, Coordinate(lat=wp.lat, lon=wp.lon, alt=wp.alt)]
        return points

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = float(alt if alt is not None else self.altitude_agl)
        ml_binding = await start_patrol_ml_runtime(
            orch,
            zones=build_zone_config(
                name="private_patrol_event_geofence",
                polygon_lonlat=self.geofence_polygon_lonlat,
            ),
            ai_tasks=list(self.ai_tasks),
        )
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_event_triggered_patrol(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await stop_patrol_ml_runtime(ml_binding)

    async def fly_event_triggered_patrol(self, orch: Orchestrator, *, cruise_alt_m: float) -> None:
        home = coord_from_home(orch.drone.home_location)
        home.alt = float(cruise_alt_m)
        report: dict[str, Any] = {
            "trigger_id": str(self.trigger_id),
            "sensor_id": str(self.sensor_id),
            "response_mode": str(self.response_mode),
            "ai_verified": False,
            "incident_focused": False,
        }

        await self._emit_trigger_events(orch, cruise_alt_m=cruise_alt_m)
        await self._configure_speed(orch)
        await asyncio.sleep(0.5)
        await orch.async_drone.arm_and_takeoff(float(cruise_alt_m))
        await self._add_event_safe(orch, "takeoff", {})

        stream_started = await self._start_stream_if_enabled(orch)
        baseline_anomalies = int(ml_runtime.status().get("anomalies_emitted", 0) or 0)

        incident_point: Coordinate | None = None
        if self.response_mode == "incident_response":
            incident_plan = self._make_incident_plan(altitude_agl=cruise_alt_m)
            incident_point = incident_plan.waypoints[0]
            await self._fly_incident_verification(
                orch,
                event_point=incident_point,
                verification_path=list(incident_plan.waypoints[1:]),
                report=report,
            )
        else:
            incident_point = await self._fly_detection_search(
                orch,
                cruise_alt_m=cruise_alt_m,
                baseline_anomalies=baseline_anomalies,
                report=report,
            )

        if incident_point is not None and report.get("ai_verified"):
            report["incident_focused"] = True

        await self._stop_stream_if_started(orch, stream_started)
        await self._return_home(orch, home)
        await self._save_trigger_report(orch, report)

        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is not None:
            await orch.repo.finish_flight(
                flight_id,
                status=FlightStatus.COMPLETED,
                note="Sensor-triggered patrol completed and returned home",
            )

    async def _emit_trigger_events(self, orch: Orchestrator, *, cruise_alt_m: float) -> None:
        loc = self.event_location_lonlat
        await self._add_event_safe(
            orch,
            "private_patrol_trigger_received",
            {
                "trigger_id": str(self.trigger_id),
                "sensor_id": str(self.sensor_id),
                "response_mode": str(self.response_mode),
                "event_location_lonlat": (
                    [float(loc[0]), float(loc[1])] if loc is not None else None
                ),
                "verification_loiter_s": float(self.verification_loiter_s),
                "auto_stream_video": bool(self.auto_stream_video),
                "record_video_stream": bool(self.record_video_stream),
                "track_target": bool(self.track_target),
                "target_label": str(self.target_label).strip() if self.target_label else None,
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ai_configured",
            {
                "tasks": list(self.ai_tasks),
                "dynamic_triggers": {
                    **dynamic_trigger_profile(ai_tasks=self.ai_tasks, path_offset_m=0.0),
                    "event_triggered": True,
                    "trigger_id": str(self.trigger_id),
                    "sensor_id": str(self.sensor_id),
                },
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ml_runtime",
            patrol_ml_runtime_payload(orch),
        )
        _ = cruise_alt_m

    async def _configure_speed(self, orch: Orchestrator) -> None:
        try:
            speed_set = await orch.async_drone.set_groundspeed(float(self.speed_mps))
            await self._add_event_safe(
                orch,
                "private_patrol_speed_configured",
                {"speed_mps": float(self.speed_mps), "applied": bool(speed_set)},
            )
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "private_patrol_speed_config_failed",
                {"speed_mps": float(self.speed_mps), "error": str(exc)},
            )

    async def _start_stream_if_enabled(self, orch: Orchestrator) -> bool:
        stream_started = False
        if self.auto_stream_video:
            stream_started = await self._start_video_stream(orch)
        await self._add_event_safe(
            orch,
            "private_patrol_stream_video_to_operator",
            {
                "requested": bool(self.auto_stream_video),
                "started": bool(stream_started),
            },
        )
        return stream_started

    async def _stop_stream_if_started(self, orch: Orchestrator, stream_started: bool) -> None:
        if stream_started:
            stopped = await self._stop_video_stream(orch)
            await self._add_event_safe(
                orch,
                "private_patrol_stream_video_stopped",
                {"stopped": bool(stopped)},
            )

