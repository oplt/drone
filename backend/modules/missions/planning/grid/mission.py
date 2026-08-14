from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from backend.core.types.geo import coord_from_home
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.planning.grid.constants import (
    MAX_GRID_PATH_POINTS,
    AgricultureMode,
)
from backend.modules.missions.planning.grid.geo import (
    _maybe_get_batch_elevation_provider,
    _maybe_get_elevation_provider,
    _poly_centroid_lonlat,
)
from backend.modules.missions.planning.grid.models import (
    _validate_plan_limits,
    combine_grid_plans,
)
from backend.modules.missions.planning.grid.planner import GridPlanner
from backend.modules.missions.planning.terrain_follow import (
    apply_terrain_follow_to_path,
    resolve_home_amsl_m,
)
from backend.modules.vehicle_runtime.types import Coordinate

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GridMission:
    """Agricultural lawnmower mission over a field polygon.

    Usage A – pre-computed waypoints
    ---------------------------------
    Provide ``waypoints`` (≥ 2 Coordinates); planning is skipped.

    Usage B – polygon-driven planning (preferred for agri tasks)
    -------------------------------------------------------------
    Provide ``field_polygon_lonlat`` and leave ``waypoints`` empty.
    The planner runs inside ``fly_grid()`` so elevation data is available.

    The class is **frozen** (immutable after construction) for safety.
    Internal state mutations during planning use ``object.__setattr__``,
    which is the standard pattern for frozen dataclasses.
    """

    # --- Required / core ---
    cruise_alt_m: float = 30.0

    # --- Mission mode ---
    mode: AgricultureMode = "mapping"

    # --- Waypoints (pre-computed or filled by planner) ---
    waypoints: list[Coordinate] = field(default_factory=list)
    work_leg_mask: list[bool] = field(default_factory=list)

    # --- Polygon-driven planning ---
    field_polygon_lonlat: list[tuple[float, float]] | None = None  # [(lon, lat), …]
    row_spacing_m: float = 7.5
    grid_angle_deg: float | None = None  # None + slope_aware → contour-aligned
    slope_aware: bool = False
    safety_inset_m: float = 1.5

    # --- Terrain following ---
    terrain_follow: bool = False
    agl_m: float = 30.0  # above-ground-level; used only when terrain_follow=True
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = 90.0
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    row_stride: int = 1
    row_phase_m: float = 0.0
    interpolate_steps: int = 6

    # ------------------------------------------------------------------
    # BaseMission interface
    # ------------------------------------------------------------------

    def get_waypoints(self) -> list[Coordinate]:
        """Called by orchestrator for pre-flight distance estimation."""
        if len(self.waypoints) >= 2:
            return list(self.waypoints)

        if not self.field_polygon_lonlat:
            raise ValueError("GridMission requires at least 2 waypoints OR field_polygon_lonlat.")

        # Return a placeholder (centroid → centroid) so the orchestrator can
        # proceed; real waypoints are computed lazily inside fly_grid().
        lon0, lat0 = _poly_centroid_lonlat(self.field_polygon_lonlat)
        c = Coordinate(lat=lat0, lon=lon0, alt=self.cruise_alt_m)
        return [c, c]

    async def execute(self, orch: Orchestrator, *, alt: float = 30.0) -> None:
        """Entry point called by the generic execute_mission runner."""
        # Allow caller-supplied alt to override cruise_alt_m.
        if alt != self.cruise_alt_m:
            object.__setattr__(self, "cruise_alt_m", alt)
        effective_alt = float(self.agl_m if self.terrain_follow else self.cruise_alt_m)
        await orch.run_mission(
            self,
            alt=effective_alt,
            flight_fn=lambda: self.fly_grid(orch),
        )

    # ------------------------------------------------------------------
    # Planning + execution
    # ------------------------------------------------------------------

    async def fly_grid(self, orch: Orchestrator) -> None:
        """Plan (if needed) and fly the lawnmower route."""
        if len(self.waypoints) < 2:
            if not self.field_polygon_lonlat:
                raise ValueError("GridMission needs ≥ 2 waypoints or field_polygon_lonlat.")
            await self._plan_grid(orch)

        anchors = self._build_route(orch, cruise_alt=self.cruise_alt_m)
        await self._stitch_path(orch, anchors)

    async def _plan_grid(self, orch: Orchestrator) -> None:
        """Run GridPlanner and (optionally) apply terrain following."""
        elev = _maybe_get_elevation_provider(orch)
        batch_elev = _maybe_get_batch_elevation_provider(orch)
        angle: float | None = self.grid_angle_deg
        spacing = float(self.row_spacing_m)

        if self.slope_aware:
            if elev is None:
                logger.warning(
                    "GridMission: slope_aware=True but no elevation provider found; "
                    "falling back to angle=0°"
                )
                angle = angle if angle is not None else 0.0
            else:
                if batch_elev is not None:
                    gxgy = GridPlanner.estimate_mean_gradient_batched(
                        self.field_polygon_lonlat,
                        batch_elev,
                    )
                else:
                    gxgy = GridPlanner.estimate_mean_gradient(self.field_polygon_lonlat, elev)
                if angle is None:
                    angle = GridPlanner.contour_aligned_angle_deg(gxgy)
                spacing = GridPlanner.slope_corrected_spacing_m(spacing, float(angle), gxgy)

        if angle is None:
            angle = 0.0

        primary = GridPlanner.generate(
            self.field_polygon_lonlat,
            spacing_m=float(spacing),
            angle_deg=float(angle),
            inset_m=float(self.safety_inset_m),
            start_corner=self.start_corner,
            lane_strategy=self.lane_strategy,
            row_stride=max(1, int(self.row_stride)),
            row_phase_m=float(self.row_phase_m),
        )
        plans = [primary]

        if self.pattern_mode == "crosshatch":
            angle2 = (float(angle) + float(self.crosshatch_angle_offset_deg)) % 180.0
            if not math.isclose(angle2, float(angle), abs_tol=1e-6):
                secondary = GridPlanner.generate(
                    self.field_polygon_lonlat,
                    spacing_m=float(spacing),
                    angle_deg=float(angle2),
                    inset_m=float(self.safety_inset_m),
                    start_corner=self.start_corner,
                    lane_strategy=self.lane_strategy,
                    row_stride=max(1, int(self.row_stride)),
                    row_phase_m=float(self.row_phase_m),
                )
                plans.append(secondary)

        plan = combine_grid_plans(
            plans=plans,
            poly_lonlat=self.field_polygon_lonlat,
            pattern_mode=self.pattern_mode,
        )
        _validate_plan_limits(plan)

        object.__setattr__(self, "waypoints", plan.waypoints)
        object.__setattr__(self, "work_leg_mask", plan.work_leg_mask)

        # Log the plan to the flight event repo.
        await self._add_event_safe(
            orch,
            "grid_planned",
            {"angle_deg": plan.angle_deg, "spacing_m": plan.spacing_m, **plan.stats},
        )
        logger.info(
            "Grid planned: mode=%s rows=%d waypoints=%d route=%.0f m",
            self.pattern_mode,
            plan.stats["rows"],
            plan.stats["waypoints"],
            plan.stats["route_m"],
        )

        # Terrain following is applied after interpolation in _stitch_path()
        # so altitude remains terrain-aware across the full flown path.

    # ------------------------------------------------------------------
    # Stubs - these are provided by BaseMission in the real codebase.
    # Defined here so the file is self-consistent for type checking.
    # ------------------------------------------------------------------

    async def _add_event_safe(
        self,
        orch: Orchestrator,
        event_type: str,
        data: dict | None = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            logger.warning(
                "GridMission: skipping event '%s' because flight_id is unavailable",
                event_type,
            )
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception:
            logger.exception(
                "GridMission: failed to persist event '%s' (flight_id=%s)",
                event_type,
                flight_id,
            )

    def _build_route(self, orch: Orchestrator, *, cruise_alt: float) -> list:
        if len(self.waypoints) < 2:
            raise ValueError("GridMission requires at least 2 planned waypoints.")

        home = coord_from_home(orch.drone.home_location)
        home.alt = float(self.agl_m if self.terrain_follow else cruise_alt)

        route = [home]
        for wp in self.waypoints:
            alt = wp.alt if getattr(wp, "alt", None) is not None else cruise_alt
            route.append(Coordinate(lat=wp.lat, lon=wp.lon, alt=float(alt)))
        route.append(home)

        orch._dest_coord = route[-2]
        return route

    async def _stitch_path(self, orch: Orchestrator, anchors: list) -> None:
        if len(anchors) < 2:
            raise ValueError("Grid route requires at least 2 anchors.")

        takeoff_alt_m = float(self.agl_m if self.terrain_follow else self.cruise_alt_m)
        await asyncio.sleep(1.0)
        await orch.async_drone.arm_and_takeoff(takeoff_alt_m)

        await self._add_event_safe(orch, "takeoff", {})

        requested_steps = max(0, int(self.interpolate_steps))
        segment_count = max(1, len(anchors) - 1)
        max_steps_by_budget = max(0, (MAX_GRID_PATH_POINTS // segment_count) - 1)
        interpolate_steps = min(requested_steps, max_steps_by_budget)
        if interpolate_steps < requested_steps:
            logger.info(
                "GridMission: interpolation reduced from %d to %d for %d segments",
                requested_steps,
                interpolate_steps,
                segment_count,
            )
        path: list[Coordinate] = []
        for a, b in zip(anchors, anchors[1:]):
            seg = (
                list(orch.maps.waypoints_between(a, b, steps=interpolate_steps))
                if interpolate_steps > 0
                else [a, b]
            )
            if path and seg:
                prev = path[-1]
                first = seg[0]
                if (
                    abs(prev.lat - first.lat) <= 1e-9
                    and abs(prev.lon - first.lon) <= 1e-9
                    and abs(float(prev.alt) - float(first.alt)) <= 1e-6
                ):
                    seg = seg[1:]
            path.extend(seg)

        if not path:
            raise ValueError("GridMission produced an empty route path")

        if self.terrain_follow:
            home_amsl_m = await asyncio.to_thread(resolve_home_amsl_m, orch.drone)
            path = await apply_terrain_follow_to_path(
                maps_client=orch.maps,
                path=path,
                home_amsl_m=home_amsl_m,
                target_agl_m=float(self.agl_m),
            )
            await self._add_event_safe(
                orch,
                "grid_terrain_follow_applied",
                {
                    "path_points": len(path),
                    "target_agl_m": float(self.agl_m),
                    "takeoff_alt_m": takeoff_alt_m,
                },
            )

        await orch.async_drone.follow_waypoints(path)

        await self._add_event_safe(orch, "reached_destination", {})

        await orch.async_drone.land()
        await self._add_event_safe(orch, "landing_command_sent", {})

        await orch.async_drone.wait_until_disarmed(900)

        await self._add_event_safe(orch, "landed_home", {})
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is not None:
            try:
                await orch.repo.finish_flight(
                    flight_id,
                    status=FlightStatus.COMPLETED,
                    note="Grid mission completed and returned home",
                )
            except Exception:
                logger.exception(
                    "GridMission: failed to finish flight in repository (flight_id=%s)",
                    flight_id,
                )
