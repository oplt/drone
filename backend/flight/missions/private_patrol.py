from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Sequence

from shapely.geometry import MultiPolygon, Polygon

from backend.config import settings
from backend.db.models import FlightStatus
from backend.drone.models import Coordinate
from backend.drone.orchestrator import Orchestrator
from backend.flight.missions.grid_mission import GridPlanner, _validate_plan_limits
from backend.ml.patrol.config import ml_settings
from backend.ml.patrol.runtime import ml_runtime
from backend.utils.geo import coord_from_home

logger = logging.getLogger(__name__)

PatrolDirection = Literal["clockwise", "counterclockwise"]
PatrolTask = Literal[
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
]
PatrolTriggerType = Literal[
    "motion_sensor",
    "fence_alarm",
    "camera_detection",
    "night_schedule",
    "unknown_vehicle",
]
PatrolMissionTask = Literal[
    "perimeter_patrol",
    "waypoint_patrol",
    "grid_surveillance",
    "event_triggered_patrol",
]

PATROL_AI_TASKS: tuple[PatrolTask, ...] = (
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
)

_EVENT_TRIGGER_ACTION_MAP: dict[PatrolTriggerType, str] = {
    "motion_sensor": "drone_takeoff",
    "fence_alarm": "drone_fly_to_location",
    "camera_detection": "drone_verify_detection",
    "night_schedule": "scheduled_patrol_start",
    "unknown_vehicle": "track_target",
}

_PRIVATE_PATROL_TASK_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "perimeter_patrol",
        "label": "Perimeter Patrol Mission",
        "purpose": "Continuous surveillance of property borders.",
        "description": (
            "Generate an offset perimeter route, patrol in the selected direction, "
            "and run AI detections for rapid anomaly verification."
        ),
        "default_params": {
            "altitude_m": 30.0,
            "speed_mps": 6.0,
            "path_offset_m": 15.0,
            "direction": "clockwise",
            "camera_angle_deg": 35.0,
            "camera_overlap_pct": 50.0,
            "patrol_loops": 1,
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
    {
        "id": "waypoint_patrol",
        "label": "Waypoint Patrol (Key Points)",
        "purpose": "Monitor specific sensitive areas instead of the full perimeter.",
        "description": (
            "Visit ordered security checkpoints such as gate, parking, storage, "
            "back fence, and roof. At each point: hover, run 360° scan, and capture zoom evidence."
        ),
        "default_params": {
            "altitude_m": 30.0,
            "speed_mps": 5.0,
            "hover_time_s": 15.0,
            "camera_scan_yaw_deg": 360.0,
            "zoom_capture": True,
            "return_to_start": True,
            "example_checkpoints": [
                "Gate",
                "Garage",
                "Back yard",
                "Parking lot",
                "Warehouse doors",
                "Roof",
            ],
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
    {
        "id": "grid_surveillance",
        "label": "Grid Surveillance Mission",
        "purpose": "Full area monitoring for large private properties.",
        "description": (
            "Generate a lawnmower coverage pattern for broad-area monitoring such as "
            "farms, solar parks, estates, and construction sites."
        ),
        "default_params": {
            "altitude_m": 28.0,
            "speed_mps": 5.0,
            "grid_spacing_m": 40.0,
            "grid_angle_deg": 0.0,
            "safety_inset_m": 2.0,
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
    {
        "id": "event_triggered_patrol",
        "label": "Event-Triggered Patrol",
        "purpose": "Rapid response and visual verification triggered by security events.",
        "description": (
            "On trigger events (fence breach, motion, unknown vehicle), launch, move to "
            "event location, verify/track target, and stream verification context to operators."
        ),
        "default_params": {
            "trigger_type": "fence_alarm",
            "speed_mps": 6.0,
            "verification_loiter_s": 45.0,
            "track_target": True,
            "auto_stream_video": True,
            "verification_radius_m": 18.0,
        },
        "trigger_actions": {
            "motion_sensor": "drone_takeoff",
            "fence_alarm": "drone_fly_to_location",
            "camera_detection": "drone_verify_detection",
            "night_schedule": "scheduled_patrol_start",
            "unknown_vehicle": "track_target",
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
)

MAX_PRIVATE_PATROL_PATH_POINTS = 4_000


@dataclass(frozen=True)
class PrivatePatrolPlan:
    waypoints: list[Coordinate]
    stats: dict[str, Any]


@dataclass(frozen=True)
class PatrolMLBinding:
    enabled: bool
    running: bool
    started_here: bool
    stream_source: str | int | None
    reason: str | None = None


# ---------------------------------------------------------------------------
# Public helpers used by API endpoints
# ---------------------------------------------------------------------------

def private_patrol_task_catalog() -> list[dict[str, Any]]:
    """List available private patrol mission templates/tasks."""
    return [dict(item) for item in _PRIVATE_PATROL_TASK_CATALOG]


def normalize_ai_tasks(tasks: Iterable[str] | None) -> tuple[PatrolTask, ...]:
    if tasks is None:
        return PATROL_AI_TASKS

    normalized: list[PatrolTask] = []
    seen: set[str] = set()
    for raw in tasks:
        key = str(raw or "").strip().lower()
        if not key:
            continue
        if key not in PATROL_AI_TASKS:
            raise ValueError(
                f"Unsupported patrol AI task '{raw}'. "
                f"Supported tasks: {', '.join(PATROL_AI_TASKS)}"
            )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)  # type: ignore[arg-type]

    if not normalized:
        return PATROL_AI_TASKS
    return tuple(normalized)


def normalize_patrol_direction(direction: str | PatrolDirection | None) -> PatrolDirection:
    raw = str(direction or "clockwise").strip().lower().replace("_", "-")
    if raw in {"clockwise", "cw"}:
        return "clockwise"
    if raw in {"counterclockwise", "counter-clockwise", "ccw"}:
        return "counterclockwise"
    raise ValueError("direction must be 'clockwise' or 'counterclockwise'")


def normalize_trigger_type(trigger_type: str | PatrolTriggerType | None) -> PatrolTriggerType:
    raw = str(trigger_type or "fence_alarm").strip().lower().replace("-", "_")
    if raw not in _EVENT_TRIGGER_ACTION_MAP:
        supported = ", ".join(_EVENT_TRIGGER_ACTION_MAP.keys())
        raise ValueError(f"Unsupported trigger_type '{trigger_type}'. Supported: {supported}")
    return raw  # type: ignore[return-value]


def trigger_action_profile(
    trigger_type: str | PatrolTriggerType,
    *,
    target_label: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_trigger_type(trigger_type)
    return {
        "trigger_type": normalized,
        "action": _EVENT_TRIGGER_ACTION_MAP[normalized],
        "target_label": str(target_label).strip() if target_label else None,
    }


def estimate_camera_trigger_distance_m(
    *,
    altitude_agl_m: float,
    overlap_pct: float,
    camera_fov_v_deg: float = 62.0,
    min_spacing_m: float = 2.0,
    max_spacing_m: float = 25.0,
) -> float:
    """Estimate camera trigger distance from altitude and overlap target."""
    overlap_fraction = max(0.01, min(0.95, float(overlap_pct) / 100.0))
    footprint_m = 2.0 * float(altitude_agl_m) * math.tan(math.radians(float(camera_fov_v_deg) / 2.0))
    spacing_m = footprint_m * (1.0 - overlap_fraction)
    return max(float(min_spacing_m), min(float(max_spacing_m), float(spacing_m)))


def generate_private_patrol_plan(
    polygon_lonlat: Sequence[tuple[float, float]],
    *,
    altitude_agl_m: float,
    path_offset_m: float,
    direction: PatrolDirection,
    max_segment_length_m: float,
) -> PrivatePatrolPlan:
    """Convert a property polygon to an offset flyable perimeter path."""
    if len(polygon_lonlat) < 3:
        raise ValueError("property polygon must have at least 3 vertices")

    offset_m = float(path_offset_m)
    if offset_m < 0:
        raise ValueError("path_offset_m must be >= 0")

    segment_len_m = float(max_segment_length_m)
    if segment_len_m <= 0:
        raise ValueError("max_segment_length_m must be > 0")

    lonlat_ring = _ensure_closed_ring([(float(lon), float(lat)) for lon, lat in polygon_lonlat])
    lon0, lat0 = _poly_centroid_lonlat(lonlat_ring)

    xy_ring = [_lonlat_to_xy_m(lon, lat, lon0, lat0) for lon, lat in lonlat_ring]
    base_poly = Polygon(xy_ring)
    if not base_poly.is_valid or base_poly.area <= 0:
        raise ValueError("Invalid property polygon (self-intersection or zero area)")

    patrol_poly = base_poly
    applied_offset_m = 0.0

    # Patrol stays inside the property by default (negative buffer).
    if offset_m > 0:
        offset_candidate = _largest_polygon(base_poly.buffer(-offset_m))
        if offset_candidate is not None and offset_candidate.area > 0:
            patrol_poly = offset_candidate
            applied_offset_m = offset_m
        else:
            logger.warning(
                "PrivatePatrol: inward offset %.2fm removed polygon; falling back to boundary path",
                offset_m,
            )

    ring_xy = _strip_closed_ring([(float(x), float(y)) for x, y in patrol_poly.exterior.coords])
    if len(ring_xy) < 3:
        raise ValueError("Patrol route has fewer than 3 points after offset")

    clockwise = _is_clockwise_xy(ring_xy)
    if direction == "clockwise" and not clockwise:
        ring_xy = list(reversed(ring_xy))
    elif direction == "counterclockwise" and clockwise:
        ring_xy = list(reversed(ring_xy))

    dense_xy = _densify_ring_xy(ring_xy, max_segment_length_m=segment_len_m)
    if len(dense_xy) < 3:
        raise ValueError("Patrol route generation failed: too few route points")

    closed_dense_xy = dense_xy + [dense_xy[0]]
    waypoints: list[Coordinate] = []
    for x, y in closed_dense_xy:
        lon, lat = _xy_m_to_lonlat(x, y, lon0, lat0)
        waypoints.append(Coordinate(lat=lat, lon=lon, alt=float(altitude_agl_m)))

    route_m = _polyline_length_m(closed_dense_xy)
    stats = {
        "direction": direction,
        "path_offset_requested_m": round(offset_m, 2),
        "path_offset_applied_m": round(applied_offset_m, 2),
        "raw_vertices": len(_strip_closed_ring(lonlat_ring)),
        "planned_vertices": len(dense_xy),
        "perimeter_m": round(route_m, 1),
        "area_m2": round(float(base_poly.area), 1),
    }
    return PrivatePatrolPlan(waypoints=waypoints, stats=stats)


def generate_waypoint_patrol_plan(
    key_points_lonlat: Sequence[tuple[float, float]],
    *,
    altitude_agl_m: float,
    return_to_start: bool,
) -> PrivatePatrolPlan:
    """Build ordered key-point patrol route with optional return to first checkpoint."""
    if len(key_points_lonlat) < 2:
        raise ValueError("Waypoint patrol requires at least 2 key points")

    key_points: list[tuple[float, float]] = []
    for lon, lat in key_points_lonlat:
        lon_f = float(lon)
        lat_f = float(lat)
        if not (-180.0 <= lon_f <= 180.0 and -90.0 <= lat_f <= 90.0):
            raise ValueError("Invalid key point coordinates")
        key_points.append((lon_f, lat_f))

    route_points = list(key_points)
    if return_to_start and key_points and route_points[0] != route_points[-1]:
        route_points.append(route_points[0])

    waypoints = [
        Coordinate(lat=lat, lon=lon, alt=float(altitude_agl_m))
        for lon, lat in route_points
    ]
    route_m = _route_length_for_coords(waypoints)
    return PrivatePatrolPlan(
        waypoints=waypoints,
        stats={
            "task_type": "waypoint_patrol",
            "key_points": len(key_points),
            "waypoints": len(waypoints),
            "return_to_start": bool(return_to_start),
            "route_m": round(route_m, 1),
        },
    )


def generate_grid_surveillance_plan(
    polygon_lonlat: Sequence[tuple[float, float]],
    *,
    altitude_agl_m: float,
    grid_spacing_m: float,
    grid_angle_deg: float,
    safety_inset_m: float,
) -> PrivatePatrolPlan:
    """Build a coverage grid plan for large-area private surveillance."""
    if len(polygon_lonlat) < 3:
        raise ValueError("Grid surveillance requires a polygon with at least 3 vertices")
    spacing = float(grid_spacing_m)
    if spacing <= 0:
        raise ValueError("grid_spacing_m must be > 0")

    poly = [(float(lon), float(lat)) for lon, lat in polygon_lonlat]
    plan = GridPlanner.generate(
        poly,
        spacing_m=spacing,
        angle_deg=float(grid_angle_deg),
        inset_m=max(0.0, float(safety_inset_m)),
        lane_strategy="serpentine",
        start_corner="auto",
    )
    _validate_plan_limits(plan)

    waypoints = [
        Coordinate(lat=float(wp.lat), lon=float(wp.lon), alt=float(altitude_agl_m))
        for wp in plan.waypoints
    ]
    return PrivatePatrolPlan(
        waypoints=waypoints,
        stats={
            "task_type": "grid_surveillance",
            "rows": int(plan.stats.get("rows", 0)),
            "waypoints": len(waypoints),
            "route_m": round(float(plan.stats.get("route_m", 0.0) or 0.0), 1),
            "area_m2": round(float(plan.stats.get("area_m2", 0.0) or 0.0), 1),
            "grid_spacing_m": round(float(plan.spacing_m), 2),
            "grid_angle_deg": round(float(plan.angle_deg), 2),
            "safety_inset_m": round(float(safety_inset_m), 2),
        },
    )


def generate_event_triggered_patrol_plan(
    event_location_lonlat: tuple[float, float],
    *,
    altitude_agl_m: float,
    verification_radius_m: float,
) -> PrivatePatrolPlan:
    """Build a short verification pattern centered on the trigger location."""
    lon = float(event_location_lonlat[0])
    lat = float(event_location_lonlat[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise ValueError("Invalid trigger event location coordinates")

    radius_m = max(0.0, float(verification_radius_m))
    offsets_m: list[tuple[float, float]] = [(0.0, 0.0)]
    if radius_m > 0.0:
        offsets_m.extend(
            [
                (radius_m, 0.0),
                (0.0, radius_m),
                (-radius_m, 0.0),
                (0.0, -radius_m),
                (0.0, 0.0),
            ]
        )

    waypoints: list[Coordinate] = []
    for dx_m, dy_m in offsets_m:
        wp_lon = lon + (dx_m / _meters_per_deg_lon(lat))
        wp_lat = lat + (dy_m / _meters_per_deg_lat())
        waypoints.append(
            Coordinate(lat=float(wp_lat), lon=float(wp_lon), alt=float(altitude_agl_m))
        )

    route_m = _route_length_for_coords(waypoints)
    return PrivatePatrolPlan(
        waypoints=waypoints,
        stats={
            "task_type": "event_triggered_patrol",
            "event_location_lonlat": [round(lon, 7), round(lat, 7)],
            "verification_radius_m": round(radius_m, 2),
            "waypoints": len(waypoints),
            "verification_route_m": round(route_m, 1),
        },
    )


def repeat_patrol_loops(waypoints: Sequence[Coordinate], loops: int) -> list[Coordinate]:
    if not waypoints:
        return []

    loop_count = max(1, int(loops))
    closed = len(waypoints) >= 2 and _coords_close(waypoints[0], waypoints[-1])
    base = list(waypoints[:-1] if closed else waypoints)
    if not base:
        return list(waypoints)

    out: list[Coordinate] = []
    for i in range(loop_count):
        segment = list(base)
        if i > 0 and out and segment and _coords_close(out[-1], segment[0]):
            segment = segment[1:]
        out.extend(segment)

    if len(out) >= 2 and not _coords_close(out[0], out[-1]):
        first = out[0]
        out.append(Coordinate(lat=first.lat, lon=first.lon, alt=first.alt))

    return out


def _resolve_patrol_ml_stream_source(orch: Orchestrator) -> str | int | None:
    configured_source = getattr(ml_settings, "stream_source", None)
    if configured_source not in {None, ""}:
        return configured_source

    video = getattr(orch, "video", None)
    video_source = getattr(video, "source", None)
    if video_source not in {None, ""}:
        return video_source

    if settings.drone_video_use_gazebo:
        return settings.drone_video_source_gazebo

    if settings.drone_video_enabled:
        return settings.drone_video_source

    return None


def _build_zone_config(
    *,
    name: str,
    polygon_lonlat: Sequence[tuple[float, float]] | None,
) -> list[dict[str, Any]]:
    if not polygon_lonlat or len(polygon_lonlat) < 3:
        return []

    polygon = [
        {"lat": float(lat), "lon": float(lon)}
        for lon, lat in polygon_lonlat
    ]
    return [{"name": name, "polygon": polygon, "restricted": True}]


async def _start_patrol_ml_runtime(
    orch: Orchestrator,
    *,
    zones: list[dict[str, Any]] | None = None,
) -> PatrolMLBinding:
    stream_source = _resolve_patrol_ml_stream_source(orch)
    if not ml_settings.enabled:
        return PatrolMLBinding(
            enabled=False,
            running=False,
            started_here=False,
            stream_source=stream_source,
            reason="ML pipeline disabled",
        )

    if stream_source in {None, ""}:
        return PatrolMLBinding(
            enabled=True,
            running=False,
            started_here=False,
            stream_source=stream_source,
            reason="No patrol video source configured",
        )

    try:
        status = ml_runtime.status()
        if bool(status.get("running")):
            if zones:
                ml_runtime.set_zones(zones)
            return PatrolMLBinding(
                enabled=True,
                running=True,
                started_here=False,
                stream_source=stream_source,
            )

        await ml_runtime.start(stream_source=stream_source)
        if zones:
            ml_runtime.set_zones(zones)
        return PatrolMLBinding(
            enabled=True,
            running=True,
            started_here=True,
            stream_source=stream_source,
        )
    except Exception as exc:
        logger.exception("Failed to start patrol ML runtime")
        return PatrolMLBinding(
            enabled=True,
            running=False,
            started_here=False,
            stream_source=stream_source,
            reason=str(exc),
        )


async def _stop_patrol_ml_runtime(binding: PatrolMLBinding) -> bool:
    if not binding.started_here:
        return False

    try:
        await ml_runtime.stop()
        return True
    except Exception:
        logger.exception("Failed to stop patrol ML runtime")
        return False


def _patrol_ml_runtime_payload(orch: Orchestrator) -> dict[str, Any]:
    status = ml_runtime.status() if ml_settings.enabled else {}
    return {
        "enabled": bool(ml_settings.enabled),
        "running": bool(status.get("running", False)),
        "task_state": status.get("task_state"),
        "stream_source": _resolve_patrol_ml_stream_source(orch),
        "frames_processed": int(status.get("frames_processed", 0) or 0),
        "anomalies_emitted": int(status.get("anomalies_emitted", 0) or 0),
        "last_error": status.get("last_error"),
    }


# ---------------------------------------------------------------------------
# Mission implementation
# ---------------------------------------------------------------------------

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

        object.__setattr__(self, "patrol_direction", normalize_patrol_direction(self.patrol_direction))
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
        ml_binding = await _start_patrol_ml_runtime(
            orch,
            zones=_build_zone_config(
                name="private_patrol_property",
                polygon_lonlat=self.polygon_lonlat,
            ),
        )
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_private_patrol(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await _stop_patrol_ml_runtime(ml_binding)

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
        total_route_m = _route_length_for_coords(route_anchors)
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
                "dynamic_triggers": _dynamic_trigger_profile(
                    ai_tasks=self.ai_tasks,
                    path_offset_m=float(self.path_offset_m),
                ),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ml_runtime",
            _patrol_ml_runtime_payload(orch),
        )

        try:
            speed_set = await asyncio.to_thread(orch.drone.set_groundspeed, float(self.speed_mps))
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
        await asyncio.to_thread(orch.drone.arm_and_takeoff, float(cruise_alt_m))
        await self._add_event_safe(orch, "takeoff", {})

        capture_started = False
        try:
            capture_started = bool(
                await asyncio.to_thread(
                    orch.drone.start_image_capture,
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
            if path and seg and _coords_close(path[-1], seg[0]):
                seg = seg[1:]
            path.extend(seg)

        if not path:
            raise ValueError("Private patrol generated an empty flight path")

        try:
            await asyncio.to_thread(orch.drone.follow_waypoints, path)
            await self._add_event_safe(orch, "reached_destination", {})
        finally:
            if capture_started:
                try:
                    stopped = bool(await asyncio.to_thread(orch.drone.stop_image_capture))
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

        await asyncio.to_thread(orch.drone.land)
        await self._add_event_safe(orch, "landing_command_sent", {})

        await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
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


@dataclass(frozen=True)
class WaypointPatrolMission:
    key_points_lonlat: list[tuple[float, float]]
    altitude_agl: float = 30.0
    speed_mps: float = 5.0
    hover_time_s: float = 15.0
    camera_scan_yaw_deg: float = 360.0
    zoom_capture: bool = True
    return_to_start: bool = True
    ai_tasks: tuple[PatrolTask, ...] = PATROL_AI_TASKS

    mission_type: str = "private_patrol_waypoint"

    def __post_init__(self) -> None:
        if len(self.key_points_lonlat) < 2:
            raise ValueError("Waypoint patrol requires at least 2 key points")
        if float(self.altitude_agl) <= 0:
            raise ValueError("altitude_agl must be > 0")
        if float(self.speed_mps) <= 0:
            raise ValueError("speed_mps must be > 0")
        if float(self.hover_time_s) <= 0:
            raise ValueError("hover_time_s must be > 0")
        if not 0.0 <= float(self.camera_scan_yaw_deg) <= 360.0:
            raise ValueError("camera_scan_yaw_deg must be between 0 and 360")
        object.__setattr__(self, "ai_tasks", normalize_ai_tasks(self.ai_tasks))

    def _make_plan(self, *, altitude_agl: float | None = None) -> PrivatePatrolPlan:
        return generate_waypoint_patrol_plan(
            self.key_points_lonlat,
            altitude_agl_m=float(self.altitude_agl if altitude_agl is None else altitude_agl),
            return_to_start=bool(self.return_to_start),
        )

    def get_waypoints(self) -> list[Coordinate]:
        return self._make_plan().waypoints

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = float(alt if alt is not None else self.altitude_agl)
        ml_binding = await _start_patrol_ml_runtime(orch)
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_waypoint_patrol(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await _stop_patrol_ml_runtime(ml_binding)

    async def fly_waypoint_patrol(self, orch: Orchestrator, *, cruise_alt_m: float) -> None:
        plan = self._make_plan(altitude_agl=cruise_alt_m)
        keypoints = plan.waypoints
        if len(keypoints) < 2:
            raise ValueError("Waypoint patrol route requires at least 2 points")

        home = coord_from_home(orch.drone.home_location)
        home.alt = float(cruise_alt_m)

        await self._add_event_safe(
            orch,
            "private_patrol_waypoint_plan_generated",
            {
                **plan.stats,
                "speed_mps": float(self.speed_mps),
                "hover_time_s": float(self.hover_time_s),
                "camera_scan_yaw_deg": float(self.camera_scan_yaw_deg),
                "zoom_capture": bool(self.zoom_capture),
                "ai_tasks": list(self.ai_tasks),
            },
        )

        await self._add_event_safe(
            orch,
            "private_patrol_ai_configured",
            {
                "tasks": list(self.ai_tasks),
                "dynamic_triggers": _dynamic_trigger_profile(
                    ai_tasks=self.ai_tasks,
                    path_offset_m=0.0,
                ),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ml_runtime",
            _patrol_ml_runtime_payload(orch),
        )

        try:
            speed_set = await asyncio.to_thread(orch.drone.set_groundspeed, float(self.speed_mps))
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
        await asyncio.to_thread(orch.drone.arm_and_takeoff, float(cruise_alt_m))
        await self._add_event_safe(orch, "takeoff", {})

        for idx, checkpoint in enumerate(keypoints, start=1):
            await asyncio.to_thread(orch.drone.follow_waypoints, [checkpoint])
            orch._dest_coord = checkpoint
            await self._add_event_safe(
                orch,
                "private_patrol_checkpoint_arrived",
                {
                    "index": idx,
                    "lat": float(checkpoint.lat),
                    "lon": float(checkpoint.lon),
                },
            )
            await self._run_checkpoint_actions(
                orch,
                checkpoint_index=idx,
                checkpoint=checkpoint,
            )

        await asyncio.to_thread(orch.drone.follow_waypoints, [home])
        await self._add_event_safe(orch, "reached_destination", {})

        await asyncio.to_thread(orch.drone.land)
        await self._add_event_safe(orch, "landing_command_sent", {})

        await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
        await self._add_event_safe(orch, "landed_home", {})

        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is not None:
            await orch.repo.finish_flight(
                flight_id,
                status=FlightStatus.COMPLETED,
                note="Private waypoint patrol completed and returned home",
            )

    async def _run_checkpoint_actions(
        self,
        orch: Orchestrator,
        *,
        checkpoint_index: int,
        checkpoint: Coordinate,
    ) -> None:
        started = asyncio.get_running_loop().time()
        scan_result = await self._camera_scan(orch)
        zoom_result = await self._zoom_capture(orch)
        elapsed = asyncio.get_running_loop().time() - started
        remaining_hover_s = max(0.0, float(self.hover_time_s) - elapsed)
        if remaining_hover_s > 0.0:
            await asyncio.sleep(remaining_hover_s)

        await self._add_event_safe(
            orch,
            "private_patrol_checkpoint_actions_completed",
            {
                "index": int(checkpoint_index),
                "lat": float(checkpoint.lat),
                "lon": float(checkpoint.lon),
                "hover_time_s": float(self.hover_time_s),
                "camera_scan_yaw_deg": float(self.camera_scan_yaw_deg),
                "camera_scan_applied": bool(scan_result.get("applied")),
                "camera_scan_method": scan_result.get("method"),
                "zoom_capture": bool(self.zoom_capture),
                "zoom_capture_applied": bool(zoom_result.get("applied")),
                "zoom_capture_method": zoom_result.get("method"),
            },
        )

    async def _camera_scan(self, orch: Orchestrator) -> dict[str, Any]:
        if float(self.camera_scan_yaw_deg) <= 0:
            return {"applied": False, "method": None}

        method_specs: list[tuple[str, dict[str, Any]]] = [
            ("scan_yaw_360", {}),
            ("camera_scan_360", {}),
            ("condition_yaw", {"heading_deg": float(self.camera_scan_yaw_deg)}),
            ("set_yaw", {"yaw_deg": float(self.camera_scan_yaw_deg)}),
        ]
        for method_name, kwargs in method_specs:
            fn = getattr(orch.drone, method_name, None)
            if not callable(fn):
                continue
            try:
                await asyncio.to_thread(fn, **kwargs)
                return {"applied": True, "method": method_name}
            except TypeError:
                try:
                    await asyncio.to_thread(fn, float(self.camera_scan_yaw_deg))
                    return {"applied": True, "method": method_name}
                except Exception:
                    continue
            except Exception:
                continue

        return {"applied": False, "method": None}

    async def _zoom_capture(self, orch: Orchestrator) -> dict[str, Any]:
        if not self.zoom_capture:
            return {"applied": False, "method": None}

        method_specs: list[tuple[str, dict[str, Any]]] = [
            ("capture_zoom_photo", {"zoom_level": 2.0}),
            ("capture_photo", {}),
            ("trigger_camera_capture", {}),
        ]
        for method_name, kwargs in method_specs:
            fn = getattr(orch.drone, method_name, None)
            if not callable(fn):
                continue
            try:
                await asyncio.to_thread(fn, **kwargs)
                return {"applied": True, "method": method_name}
            except TypeError:
                try:
                    await asyncio.to_thread(fn)
                    return {"applied": True, "method": method_name}
                except Exception:
                    continue
            except Exception:
                continue

        start_capture = getattr(orch.drone, "start_image_capture", None)
        stop_capture = getattr(orch.drone, "stop_image_capture", None)
        if callable(start_capture) and callable(stop_capture):
            try:
                started = bool(
                    await asyncio.to_thread(
                        start_capture,
                        mode="time",
                        interval_s=0.7,
                    )
                )
                await asyncio.sleep(1.2)
                await asyncio.to_thread(stop_capture)
                return {"applied": started, "method": "start_image_capture(time)"}
            except Exception:
                return {"applied": False, "method": None}

        return {"applied": False, "method": None}

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
                "WaypointPatrolMission: failed to persist event '%s' for flight_id=%s",
                event_type,
                flight_id,
            )


@dataclass(frozen=True)
class EventTriggeredPatrolMission:
    trigger_type: PatrolTriggerType = "fence_alarm"
    event_location_lonlat: tuple[float, float] = (0.0, 0.0)
    altitude_agl: float = 30.0
    speed_mps: float = 6.0
    verification_loiter_s: float = 45.0
    track_target: bool = True
    auto_stream_video: bool = True
    verification_radius_m: float = 18.0
    target_label: str | None = None
    ai_tasks: tuple[PatrolTask, ...] = PATROL_AI_TASKS
    interpolate_steps: int = 6

    mission_type: str = "private_patrol_event_triggered"

    def __post_init__(self) -> None:
        lon = float(self.event_location_lonlat[0])
        lat = float(self.event_location_lonlat[1])
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("event_location_lonlat must be valid [lon, lat]")
        if float(self.altitude_agl) <= 0:
            raise ValueError("altitude_agl must be > 0")
        if float(self.speed_mps) <= 0:
            raise ValueError("speed_mps must be > 0")
        if float(self.verification_loiter_s) < 0:
            raise ValueError("verification_loiter_s must be >= 0")
        if float(self.verification_radius_m) < 0:
            raise ValueError("verification_radius_m must be >= 0")
        object.__setattr__(self, "trigger_type", normalize_trigger_type(self.trigger_type))
        object.__setattr__(self, "ai_tasks", normalize_ai_tasks(self.ai_tasks))

    def _make_plan(self, *, altitude_agl: float | None = None) -> PrivatePatrolPlan:
        return generate_event_triggered_patrol_plan(
            self.event_location_lonlat,
            altitude_agl_m=float(self.altitude_agl if altitude_agl is None else altitude_agl),
            verification_radius_m=float(self.verification_radius_m),
        )

    def get_waypoints(self) -> list[Coordinate]:
        points = self._make_plan().waypoints
        if len(points) == 1:
            wp = points[0]
            return [wp, Coordinate(lat=wp.lat, lon=wp.lon, alt=wp.alt)]
        return points

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = float(alt if alt is not None else self.altitude_agl)
        ml_binding = await _start_patrol_ml_runtime(orch)
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_event_triggered_patrol(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await _stop_patrol_ml_runtime(ml_binding)

    async def fly_event_triggered_patrol(self, orch: Orchestrator, *, cruise_alt_m: float) -> None:
        plan = self._make_plan(altitude_agl=cruise_alt_m)
        waypoints = plan.waypoints
        if not waypoints:
            raise ValueError("Event-triggered patrol requires a valid event location")

        event_point = waypoints[0]
        home = coord_from_home(orch.drone.home_location)
        home.alt = float(cruise_alt_m)

        await self._add_event_safe(
            orch,
            "private_patrol_trigger_received",
            {
                **trigger_action_profile(self.trigger_type, target_label=self.target_label),
                "event_location_lonlat": [float(event_point.lon), float(event_point.lat)],
                "verification_loiter_s": float(self.verification_loiter_s),
                "auto_stream_video": bool(self.auto_stream_video),
                "track_target": bool(self.track_target),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ai_configured",
            {
                "tasks": list(self.ai_tasks),
                "dynamic_triggers": {
                    **_dynamic_trigger_profile(ai_tasks=self.ai_tasks, path_offset_m=0.0),
                    "event_triggered": True,
                    "trigger_type": str(self.trigger_type),
                },
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ml_runtime",
            _patrol_ml_runtime_payload(orch),
        )

        try:
            speed_set = await asyncio.to_thread(orch.drone.set_groundspeed, float(self.speed_mps))
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

        await asyncio.sleep(0.5)
        await asyncio.to_thread(orch.drone.arm_and_takeoff, float(cruise_alt_m))
        await self._add_event_safe(orch, "takeoff", {})

        await asyncio.to_thread(orch.drone.follow_waypoints, [event_point])
        orch._dest_coord = event_point
        await self._add_event_safe(
            orch,
            "private_patrol_event_location_reached",
            {"lat": float(event_point.lat), "lon": float(event_point.lon)},
        )

        stream_started = False
        if self.auto_stream_video:
            stream_started = await self._start_video_stream(orch)
        await self._add_event_safe(
            orch,
            "private_patrol_stream_video_to_operator",
            {"requested": bool(self.auto_stream_video), "started": bool(stream_started)},
        )

        tracking_started, tracking_method = (False, None)
        if self.track_target:
            tracking_started, tracking_method = await self._start_tracking(orch, event_point)
        await self._add_event_safe(
            orch,
            "private_patrol_tracking_started",
            {
                "requested": bool(self.track_target),
                "started": bool(tracking_started),
                "method": tracking_method,
                "target_label": str(self.target_label).strip() if self.target_label else None,
            },
        )

        verification_path = list(waypoints[1:])
        if verification_path:
            await asyncio.to_thread(orch.drone.follow_waypoints, verification_path)
            await self._add_event_safe(
                orch,
                "private_patrol_event_verification_path_completed",
                {"waypoints": len(verification_path)},
            )

        if float(self.verification_loiter_s) > 0:
            await asyncio.sleep(float(self.verification_loiter_s))
            await self._add_event_safe(
                orch,
                "private_patrol_event_verification_loiter_completed",
                {"duration_s": float(self.verification_loiter_s)},
            )

        if tracking_started:
            tracking_stopped = await self._stop_tracking(orch)
            await self._add_event_safe(
                orch,
                "private_patrol_tracking_stopped",
                {"stopped": bool(tracking_stopped), "method": tracking_method},
            )

        if stream_started:
            stopped = await self._stop_video_stream(orch)
            await self._add_event_safe(
                orch,
                "private_patrol_stream_video_stopped",
                {"stopped": bool(stopped)},
            )

        await asyncio.to_thread(orch.drone.follow_waypoints, [home])
        await self._add_event_safe(orch, "reached_destination", {})

        await asyncio.to_thread(orch.drone.land)
        await self._add_event_safe(orch, "landing_command_sent", {})

        await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
        await self._add_event_safe(orch, "landed_home", {})

        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is not None:
            await orch.repo.finish_flight(
                flight_id,
                status=FlightStatus.COMPLETED,
                note="Private event-triggered patrol completed and returned home",
            )

    async def _start_video_stream(self, orch: Orchestrator) -> bool:
        start_video = getattr(orch.drone, "start_video_recording", None)
        if callable(start_video):
            try:
                return bool(await asyncio.to_thread(start_video))
            except Exception:
                return False
        return False

    async def _stop_video_stream(self, orch: Orchestrator) -> bool:
        stop_video = getattr(orch.drone, "stop_video_recording", None)
        if callable(stop_video):
            try:
                return bool(await asyncio.to_thread(stop_video))
            except Exception:
                return False
        return False

    async def _start_tracking(
        self,
        orch: Orchestrator,
        event_point: Coordinate,
    ) -> tuple[bool, str | None]:
        method_names = [
            "start_tracking",
            "start_target_tracking",
            "start_object_tracking",
            "track_target",
        ]
        for method_name in method_names:
            fn = getattr(orch.drone, method_name, None)
            if not callable(fn):
                continue
            try:
                result = await asyncio.to_thread(
                    fn,
                    target_label=(str(self.target_label).strip() if self.target_label else None),
                    lat=float(event_point.lat),
                    lon=float(event_point.lon),
                )
                return bool(result if result is not None else True), method_name
            except TypeError:
                try:
                    result = await asyncio.to_thread(fn, event_point)
                    return bool(result if result is not None else True), method_name
                except TypeError:
                    try:
                        result = await asyncio.to_thread(fn)
                        return bool(result if result is not None else True), method_name
                    except Exception:
                        continue
                except Exception:
                    continue
            except Exception:
                continue
        return False, None

    async def _stop_tracking(self, orch: Orchestrator) -> bool:
        for method_name in ("stop_tracking", "stop_target_tracking", "stop_object_tracking"):
            fn = getattr(orch.drone, method_name, None)
            if not callable(fn):
                continue
            try:
                result = await asyncio.to_thread(fn)
                return bool(result if result is not None else True)
            except Exception:
                continue
        return False

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
                "EventTriggeredPatrolMission: failed to persist event '%s' for flight_id=%s",
                event_type,
                flight_id,
            )


@dataclass(frozen=True)
class GridSurveillanceMission:
    polygon_lonlat: list[tuple[float, float]]
    altitude_agl: float = 28.0
    speed_mps: float = 5.0
    grid_spacing_m: float = 40.0
    grid_angle_deg: float = 0.0
    safety_inset_m: float = 2.0
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
        object.__setattr__(self, "ai_tasks", normalize_ai_tasks(self.ai_tasks))

    def _make_plan(self, *, altitude_agl: float | None = None) -> PrivatePatrolPlan:
        return generate_grid_surveillance_plan(
            self.polygon_lonlat,
            altitude_agl_m=float(self.altitude_agl if altitude_agl is None else altitude_agl),
            grid_spacing_m=float(self.grid_spacing_m),
            grid_angle_deg=float(self.grid_angle_deg),
            safety_inset_m=float(self.safety_inset_m),
        )

    def get_waypoints(self) -> list[Coordinate]:
        return self._make_plan().waypoints

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = float(alt if alt is not None else self.altitude_agl)
        ml_binding = await _start_patrol_ml_runtime(
            orch,
            zones=_build_zone_config(
                name="private_patrol_grid",
                polygon_lonlat=self.polygon_lonlat,
            ),
        )
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_grid_surveillance(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await _stop_patrol_ml_runtime(ml_binding)

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

        total_route_m = _route_length_for_coords(route_anchors)
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
                "dynamic_triggers": _dynamic_trigger_profile(
                    ai_tasks=self.ai_tasks,
                    path_offset_m=0.0,
                ),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ml_runtime",
            _patrol_ml_runtime_payload(orch),
        )

        try:
            speed_set = await asyncio.to_thread(orch.drone.set_groundspeed, float(self.speed_mps))
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
        await asyncio.to_thread(orch.drone.arm_and_takeoff, float(cruise_alt_m))
        await self._add_event_safe(orch, "takeoff", {})

        trigger_distance_m = max(5.0, min(30.0, float(self.grid_spacing_m) * 0.8))
        capture_started = False
        try:
            capture_started = bool(
                await asyncio.to_thread(
                    orch.drone.start_image_capture,
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
            if path and seg and _coords_close(path[-1], seg[0]):
                seg = seg[1:]
            path.extend(seg)

        if not path:
            raise ValueError("Grid surveillance generated an empty flight path")

        try:
            await asyncio.to_thread(orch.drone.follow_waypoints, path)
            await self._add_event_safe(orch, "reached_destination", {})
        finally:
            if capture_started:
                try:
                    stopped = bool(await asyncio.to_thread(orch.drone.stop_image_capture))
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

        await asyncio.to_thread(orch.drone.land)
        await self._add_event_safe(orch, "landing_command_sent", {})

        await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
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


# ---------------------------------------------------------------------------
# Internal geometry helpers
# ---------------------------------------------------------------------------

def _meters_per_deg_lat() -> float:
    return 111_132.0


def _meters_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def _lonlat_to_xy_m(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    x = (lon - lon0) * _meters_per_deg_lon(lat0)
    y = (lat - lat0) * _meters_per_deg_lat()
    return x, y


def _xy_m_to_lonlat(x: float, y: float, lon0: float, lat0: float) -> tuple[float, float]:
    lon = lon0 + x / _meters_per_deg_lon(lat0)
    lat = lat0 + y / _meters_per_deg_lat()
    return lon, lat


def _ensure_closed_ring(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        raise ValueError("polygon must have at least 3 points")
    out = list(points)
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def _strip_closed_ring(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    out = list(points)
    if len(out) >= 2 and out[0] == out[-1]:
        return out[:-1]
    return out


def _poly_centroid_lonlat(poly_lonlat: Sequence[tuple[float, float]]) -> tuple[float, float]:
    pts = _strip_closed_ring(poly_lonlat)
    if len(pts) < 3:
        raise ValueError("polygon must have at least 3 points")
    lon0 = sum(p[0] for p in pts) / len(pts)
    lat0 = sum(p[1] for p in pts) / len(pts)
    return lon0, lat0


def _largest_polygon(geometry: Polygon | MultiPolygon) -> Polygon | None:
    if isinstance(geometry, Polygon):
        return geometry if not geometry.is_empty else None
    if isinstance(geometry, MultiPolygon):
        if not geometry.geoms:
            return None
        return max(geometry.geoms, key=lambda g: g.area, default=None)
    return None


def _ring_signed_area_xy(ring_xy: Sequence[tuple[float, float]]) -> float:
    if len(ring_xy) < 3:
        return 0.0
    area2 = 0.0
    for i in range(len(ring_xy)):
        x0, y0 = ring_xy[i]
        x1, y1 = ring_xy[(i + 1) % len(ring_xy)]
        area2 += (x0 * y1) - (x1 * y0)
    return area2 / 2.0


def _is_clockwise_xy(ring_xy: Sequence[tuple[float, float]]) -> bool:
    # Negative signed area => clockwise orientation.
    return _ring_signed_area_xy(ring_xy) < 0.0


def _polyline_length_m(points_xy: Sequence[tuple[float, float]]) -> float:
    if len(points_xy) < 2:
        return 0.0
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points_xy, points_xy[1:]):
        total += math.hypot(x2 - x1, y2 - y1)
    return float(total)


def _densify_ring_xy(
    ring_xy: Sequence[tuple[float, float]],
    *,
    max_segment_length_m: float,
) -> list[tuple[float, float]]:
    pts = list(ring_xy)
    if len(pts) < 3:
        return pts

    out: list[tuple[float, float]] = []
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(math.ceil(seg_len / max_segment_length_m)))

        for step in range(steps):
            t = step / steps
            px = x1 + (x2 - x1) * t
            py = y1 + (y2 - y1) * t
            if out and math.hypot(out[-1][0] - px, out[-1][1] - py) <= 0.01:
                continue
            out.append((px, py))

    if len(out) >= 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 0.01:
        out = out[:-1]

    return out


def _coords_close(a: Coordinate, b: Coordinate, tol: float = 1e-7) -> bool:
    return abs(float(a.lat) - float(b.lat)) <= tol and abs(float(a.lon) - float(b.lon)) <= tol


def _route_length_for_coords(coords: Sequence[Coordinate]) -> float:
    if len(coords) < 2:
        return 0.0

    lat0 = sum(float(p.lat) for p in coords) / len(coords)
    lon0 = sum(float(p.lon) for p in coords) / len(coords)
    xy = [_lonlat_to_xy_m(float(c.lon), float(c.lat), lon0, lat0) for c in coords]
    return _polyline_length_m(xy)


def _dynamic_trigger_profile(*, ai_tasks: Sequence[str], path_offset_m: float) -> dict[str, Any]:
    fence_buffer = max(2.0, min(15.0, float(path_offset_m) * 0.5 if path_offset_m > 0 else 6.0))
    return {
        "active_tasks": [str(t) for t in ai_tasks],
        "trigger_mode": "event_driven",
        "fence_breach_buffer_m": round(fence_buffer, 2),
        "verification_loiter_s": 20,
        "event_cooldown_s": 5,
    }
