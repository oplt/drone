from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal

from backend.core.types.geo import coord_from_home
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.planning.geometry import (
    coords_close,
    dynamic_trigger_profile,
    route_length_for_coords,
)
from backend.modules.patrol.planning.grid import generate_grid_surveillance_plan
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
from backend.modules.patrol.planning.types import (
    MAX_PRIVATE_PATROL_PATH_POINTS,
    PatrolTask,
)
from backend.modules.vehicle_runtime.orchestrator import Orchestrator
from backend.modules.vehicle_runtime.types import Coordinate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GridSurveillanceMission:
    polygon_lonlat: list[tuple[float, float]]
    altitude_agl: float = 28.0
    speed_mps: float = 5.0
    grid_spacing_m: float = 40.0
    grid_angle_deg: float = 0.0
    safety_inset_m: float = 2.0
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = 90.0
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    row_stride: int = 1
    row_phase_m: float = 0.0
    record_video_stream: bool = True
    ai_tasks: tuple[PatrolTask, ...] = PATROL_AI_TASKS
    interpolate_steps: int = 6

    mission_type: str = "private_patrol_grid"

    def __post_init__(self) -> None:
        if len(self.polygon_lonlat) < 3:
            raise ValueError("Grid surveillance requires a polygon with at least 3 points")
        if float(self.altitude_agl) <= 0:
            raise ValueError("altitude_agl must be > 0")
        if float(self.speed_mps) <= 0:
            raise ValueError("speed_mps must be > 0")
        if float(self.grid_spacing_m) <= 0:
            raise ValueError("grid_spacing_m must be > 0")
        if not 0.0 <= float(self.grid_angle_deg) < 180.0:
            raise ValueError("grid_angle_deg must be between 0 and <180")
        if float(self.safety_inset_m) < 0:
            raise ValueError("safety_inset_m must be >= 0")
        if int(self.row_stride) < 1:
            raise ValueError("row_stride must be >= 1")
        if float(self.row_phase_m) < 0:
            raise ValueError("row_phase_m must be >= 0")
        object.__setattr__(self, "ai_tasks", normalize_ai_tasks(self.ai_tasks))

    def _make_plan(self, *, altitude_agl: float | None = None) -> PrivatePatrolPlan:
        return generate_grid_surveillance_plan(
            self.polygon_lonlat,
            altitude_agl_m=float(self.altitude_agl if altitude_agl is None else altitude_agl),
            grid_spacing_m=float(self.grid_spacing_m),
            grid_angle_deg=float(self.grid_angle_deg),
            safety_inset_m=float(self.safety_inset_m),
            pattern_mode=self.pattern_mode,
            crosshatch_angle_offset_deg=float(self.crosshatch_angle_offset_deg),
            lane_strategy=self.lane_strategy,
            start_corner=self.start_corner,
            row_stride=int(self.row_stride),
            row_phase_m=float(self.row_phase_m),
        )

    def get_waypoints(self) -> list[Coordinate]:
        return self._make_plan().waypoints

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = float(alt if alt is not None else self.altitude_agl)
        ml_binding = await start_patrol_ml_runtime(
            orch,
            zones=build_zone_config(
                name="private_patrol_grid",
                polygon_lonlat=self.polygon_lonlat,
            ),
            ai_tasks=list(self.ai_tasks),
        )
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_grid_surveillance(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await stop_patrol_ml_runtime(ml_binding)

    async def fly_grid_surveillance(self, orch: Orchestrator, *, cruise_alt_m: float) -> None:
        plan = self._make_plan(altitude_agl=cruise_alt_m)
        route_waypoints = plan.waypoints
        if len(route_waypoints) < 2:
            raise ValueError("Grid surveillance route requires at least 2 waypoints")

        home = coord_from_home(orch.drone.home_location)
        home.alt = float(cruise_alt_m)

        route_anchors = [home]
        for wp in route_waypoints:
            route_anchors.append(
                Coordinate(
                    lat=wp.lat,
                    lon=wp.lon,
                    alt=float(wp.alt if wp.alt is not None else cruise_alt_m),
                )
            )
        route_anchors.append(home)
        orch._dest_coord = route_anchors[-2]

        total_route_m = route_length_for_coords(route_anchors)
        eta_s = total_route_m / max(0.1, float(self.speed_mps))
        await self._add_event_safe(
            orch,
            "private_patrol_grid_plan_generated",
            {
                **plan.stats,
                "speed_mps": float(self.speed_mps),
                "altitude_agl_m": float(cruise_alt_m),
                "total_route_m": round(total_route_m, 1),
                "estimated_duration_s": round(eta_s, 1),
                "ai_tasks": list(self.ai_tasks),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ai_configured",
            {
                "tasks": list(self.ai_tasks),
                "dynamic_triggers": dynamic_trigger_profile(
                    ai_tasks=self.ai_tasks,
                    path_offset_m=0.0,
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

        trigger_distance_m = max(5.0, min(30.0, float(self.grid_spacing_m) * 0.8))
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
            raise ValueError("Grid surveillance generated an empty flight path")

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
                note="Private grid surveillance completed and returned home",
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
                "GridSurveillanceMission: failed to persist event '%s' for flight_id=%s",
                event_type,
                flight_id,
            )
