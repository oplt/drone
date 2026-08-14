from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.core.types.geo import coord_from_home
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.planning.camera import estimate_camera_trigger_distance_m
from backend.modules.patrol.planning.geometry import (
    coords_close,
    dynamic_trigger_profile,
    route_length_for_coords,
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
    normalize_patrol_direction,
)
from backend.modules.patrol.planning.perimeter import generate_private_patrol_plan
from backend.modules.patrol.planning.repeat import repeat_patrol_loops
from backend.modules.patrol.planning.types import (
    MAX_PRIVATE_PATROL_PATH_POINTS,
    PatrolDirection,
    PatrolTask,
)
from backend.modules.vehicle_runtime.orchestrator import Orchestrator
from backend.modules.vehicle_runtime.types import Coordinate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrivatePatrolMission:
    polygon_lonlat: list[tuple[float, float]]
    altitude_agl: float = 30.0
    speed_mps: float = 6.0
    patrol_direction: PatrolDirection = "clockwise"
    path_offset_m: float = 15.0
    loop_count: int = 1
    camera_angle_deg: float = 35.0
    camera_overlap_pct: float = 50.0
    max_segment_length_m: float = 20.0
    record_video_stream: bool = True
    ai_tasks: tuple[PatrolTask, ...] = PATROL_AI_TASKS
    interpolate_steps: int = 6

    mission_type: str = "private_patrol"

    def __post_init__(self) -> None:
        if len(self.polygon_lonlat) < 3:
            raise ValueError("Private patrol requires a polygon with at least 3 points")
        if float(self.altitude_agl) <= 0:
            raise ValueError("altitude_agl must be > 0")
        if float(self.speed_mps) <= 0:
            raise ValueError("speed_mps must be > 0")
        if float(self.path_offset_m) < 0:
            raise ValueError("path_offset_m must be >= 0")
        if int(self.loop_count) < 1:
            raise ValueError("loop_count must be >= 1")
        if not 0 <= float(self.camera_angle_deg) <= 90:
            raise ValueError("camera_angle_deg must be between 0 and 90")
        if not 0 <= float(self.camera_overlap_pct) <= 95:
            raise ValueError("camera_overlap_pct must be between 0 and 95")
        if float(self.max_segment_length_m) <= 0:
            raise ValueError("max_segment_length_m must be > 0")

        object.__setattr__(
            self, "patrol_direction", normalize_patrol_direction(self.patrol_direction)
        )
        object.__setattr__(self, "ai_tasks", normalize_ai_tasks(self.ai_tasks))

    def _make_plan(self, *, altitude_agl: float | None = None) -> PrivatePatrolPlan:
        return generate_private_patrol_plan(
            self.polygon_lonlat,
            altitude_agl_m=float(self.altitude_agl if altitude_agl is None else altitude_agl),
            path_offset_m=float(self.path_offset_m),
            direction=self.patrol_direction,
            max_segment_length_m=float(self.max_segment_length_m),
        )

    def get_waypoints(self) -> list[Coordinate]:
        plan = self._make_plan()
        return repeat_patrol_loops(plan.waypoints, loops=int(self.loop_count))

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = float(alt if alt is not None else self.altitude_agl)
        ml_binding = await start_patrol_ml_runtime(
            orch,
            zones=build_zone_config(
                name="private_patrol_property",
                polygon_lonlat=self.polygon_lonlat,
            ),
            ai_tasks=list(self.ai_tasks),
        )
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_private_patrol(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await stop_patrol_ml_runtime(ml_binding)

    async def fly_private_patrol(self, orch: Orchestrator, *, cruise_alt_m: float) -> None:
        plan = self._make_plan(altitude_agl=cruise_alt_m)
        patrol_waypoints = repeat_patrol_loops(plan.waypoints, loops=int(self.loop_count))
        if len(patrol_waypoints) < 2:
            raise ValueError("Private patrol route requires at least 2 waypoints")

        home = coord_from_home(orch.drone.home_location)
        home.alt = float(cruise_alt_m)

        route_anchors = [home]
        for wp in patrol_waypoints:
            route_anchors.append(
                Coordinate(
                    lat=wp.lat,
                    lon=wp.lon,
                    alt=float(wp.alt if wp.alt is not None else cruise_alt_m),
                )
            )
        route_anchors.append(home)

        orch._dest_coord = route_anchors[-2]

        trigger_distance_m = estimate_camera_trigger_distance_m(
            altitude_agl_m=cruise_alt_m,
            overlap_pct=float(self.camera_overlap_pct),
        )
        total_route_m = route_length_for_coords(route_anchors)
        eta_s = total_route_m / max(0.1, float(self.speed_mps))

        await self._add_event_safe(
            orch,
            "private_patrol_plan_generated",
            {
                **plan.stats,
                "loop_count": int(self.loop_count),
                "waypoints": len(patrol_waypoints),
                "total_route_m": round(total_route_m, 1),
                "estimated_duration_s": round(eta_s, 1),
                "speed_mps": float(self.speed_mps),
                "altitude_agl_m": float(cruise_alt_m),
                "camera_angle_deg": float(self.camera_angle_deg),
                "camera_overlap_pct": float(self.camera_overlap_pct),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ai_configured",
            {
                "tasks": list(self.ai_tasks),
                "dynamic_triggers": dynamic_trigger_profile(
                    ai_tasks=self.ai_tasks,
                    path_offset_m=float(self.path_offset_m),
                ),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ml_runtime",
            patrol_ml_runtime_payload(orch),
        )

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

        await asyncio.sleep(1.0)
        await orch.async_drone.arm_and_takeoff(float(cruise_alt_m))
        await self._add_event_safe(orch, "takeoff", {})

        capture_started = False
        try:
            capture_started = bool(
                await orch.async_drone.start_image_capture(
                    mode="distance",
                    distance_m=float(trigger_distance_m),
                )
            )
            await self._add_event_safe(
                orch,
                "private_patrol_capture_started",
                {
                    "mode": "distance",
                    "trigger_distance_m": round(float(trigger_distance_m), 2),
                    "started": capture_started,
                },
            )
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "private_patrol_capture_failed",
                {
                    "mode": "distance",
                    "trigger_distance_m": round(float(trigger_distance_m), 2),
                    "error": str(exc),
                },
            )

        requested_steps = max(0, int(self.interpolate_steps))
        segment_count = max(1, len(route_anchors) - 1)
        max_steps_by_budget = max(0, (MAX_PRIVATE_PATROL_PATH_POINTS // segment_count) - 1)
        interpolate_steps = min(requested_steps, max_steps_by_budget)

        path: list[Coordinate] = []
        for a, b in zip(route_anchors, route_anchors[1:]):
            seg = (
                list(orch.maps.waypoints_between(a, b, steps=interpolate_steps))
                if interpolate_steps > 0
                else [a, b]
            )
            if path and seg and coords_close(path[-1], seg[0]):
                seg = seg[1:]
            path.extend(seg)

        if not path:
            raise ValueError("Private patrol generated an empty flight path")

        try:
            await orch.async_drone.follow_waypoints(path)
            await self._add_event_safe(orch, "reached_destination", {})
        finally:
            if capture_started:
                try:
                    stopped = bool(await orch.async_drone.stop_image_capture())
                    await self._add_event_safe(
                        orch,
                        "private_patrol_capture_stopped",
                        {"stopped": stopped},
                    )
                except Exception as exc:
                    await self._add_event_safe(
                        orch,
                        "private_patrol_capture_stop_failed",
                        {"error": str(exc)},
                    )

        await orch.async_drone.land()
        await self._add_event_safe(orch, "landing_command_sent", {})

        await orch.async_drone.wait_until_disarmed(900)
        await self._add_event_safe(orch, "landed_home", {})

        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is not None:
            await orch.repo.finish_flight(
                flight_id,
                status=FlightStatus.COMPLETED,
                note="Private perimeter patrol completed and returned home",
            )

    async def _add_event_safe(
        self,
        orch: Orchestrator,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception:
            logger.exception(
                "PrivatePatrolMission: failed to persist event '%s' for flight_id=%s",
                event_type,
                flight_id,
            )


