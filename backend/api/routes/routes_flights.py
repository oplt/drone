from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from typing import Any, List, Literal, Optional, Union, Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from backend.auth.deps import require_user
from backend.db.session import Session, get_db
from backend.drone.models import Coordinate
from backend.flight.missions.grid_mission import GridMission
from backend.flight.missions.waypoints_mission import WaypointsMission
from backend.main import _build_orchestrator
from backend.messaging.websocket import telemetry_manager
from backend.flight.missions.schemas import MissionType, Waypoint


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/tasks", tags=["tasks"])


class GridMissionParams(BaseModel):
    """Parameters for a GridMission (polygon-driven lawnmower)."""
    # [[lon, lat], …] – GeoJSON coordinate order
    field_polygon_lonlat: List[List[float]] = Field(
        ..., min_length=3, description="Polygon ring as [[lon, lat], …]"
    )
    row_spacing_m: float = Field(default=7.5, gt=0, le=200)
    grid_angle_deg: Optional[float] = Field(default=None, ge=0, lt=180)
    slope_aware: bool = False
    safety_inset_m: float = Field(default=1.5, ge=0)
    terrain_follow: bool = False
    agl_m: float = Field(default=30.0, gt=0)
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = Field(default=90.0, gt=0, lt=180)
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    row_stride: int = Field(default=1, ge=1, le=20)
    row_phase_m: float = Field(default=0.0, ge=0.0, le=500.0)


class MissionProfileCamera(BaseModel):
    orientation: Literal["nadir"] = "nadir"
    fixed_exposure: bool = True
    fov_h_deg: float = Field(default=78.0, gt=1.0, lt=179.0)
    fov_v_deg: float = Field(default=62.0, gt=1.0, lt=179.0)


class MissionProfileTriggerDistance(BaseModel):
    mode: Literal["distance"] = "distance"
    distance_m: float = Field(default=2.5, gt=0.1, le=50.0)


class MissionProfileTriggerTime(BaseModel):
    mode: Literal["time"] = "time"
    interval_s: float = Field(default=1.0, gt=0.1, le=30.0)


MissionProfileTrigger = Annotated[
    Union[MissionProfileTriggerDistance, MissionProfileTriggerTime],
    Field(discriminator="mode"),
]


class PhotogrammetryMissionProfile(BaseModel):
    type: Literal["photogrammetry"] = "photogrammetry"
    altitude_m: float = Field(default=25.0, ge=20.0, le=30.0)
    front_overlap_pct: float = Field(default=80.0, ge=75.0, le=85.0)
    side_overlap_pct: float = Field(default=70.0, ge=65.0, le=75.0)
    speed_mps: float = Field(default=3.0, gt=0.1, le=20.0)
    trigger: MissionProfileTrigger = Field(default_factory=MissionProfileTriggerDistance)
    accuracy: Literal["standard_gnss", "rtk_ppk"] = "rtk_ppk"
    camera: MissionProfileCamera = Field(default_factory=MissionProfileCamera)


class MissionCreateIn(BaseModel):
    """
    Unified mission creation payload.

    For `mission_type = "waypoints"`: supply `waypoints` (≥ 2).
    For `mission_type = "grid"`:     supply `grid` params with polygon.
    """
    name: str = Field(default="mission", min_length=1, max_length=120)
    cruise_alt: float = Field(default=30.0, gt=0, le=500)
    mission_type: MissionType = MissionType.WAYPOINT

    # Waypoints mission data
    waypoints: Optional[List[Waypoint]] = None

    # Grid mission data
    grid: Optional[GridMissionParams] = None
    mission_profile: Optional[PhotogrammetryMissionProfile] = None

    @model_validator(mode="after")
    def _check_payload(self) -> "MissionCreateIn":
        if self.mission_type == MissionType.WAYPOINT:
            if not self.waypoints or len(self.waypoints) < 2:
                raise ValueError(
                    "mission_type='waypoints' requires at least 2 waypoints."
                )
        elif self.mission_type == MissionType.GRID:
            if self.grid is None:
                raise ValueError(
                    "mission_type='grid' requires a 'grid' object with field_polygon_lonlat."
                )
            if len(self.grid.field_polygon_lonlat) < 3:
                raise ValueError(
                    "field_polygon_lonlat must have at least 3 coordinate pairs."
                )
        if self.mission_profile is not None and self.mission_type != MissionType.GRID:
            raise ValueError("mission_profile is supported only for mission_type='grid'.")
        return self


class MissionCreateOut(BaseModel):
    flight_id: str
    status: str
    mission_name: str
    mission_type: str
    waypoints_count: int


# ---------------------------------------------------------------------------
# Orchestrator singleton
# ---------------------------------------------------------------------------

_orch_lock = asyncio.Lock()
_orch: Any = None


async def get_orchestrator() -> Any:
    global _orch
    if _orch is not None:
        return _orch
    async with _orch_lock:
        if _orch is None:               # double-checked
            _orch = await _build_orchestrator()
    return _orch


# ---------------------------------------------------------------------------
# Mission factory
# ---------------------------------------------------------------------------

def _build_mission(payload: MissionCreateIn) -> Any:
    """Return the appropriate mission object for the given payload."""
    if payload.mission_type == MissionType.WAYPOINT:
        coords = [
            Coordinate(
                lat=w.lat,
                lon=w.lon,
                alt=payload.cruise_alt if w.alt is None else w.alt,
            )
            for w in payload.waypoints  # validated non-None by model_validator
        ]
        return WaypointsMission(waypoints=coords), len(coords)

    if payload.mission_type == MissionType.GRID:
        g = payload.grid  # validated non-None by model_validator
        profile = payload.mission_profile

        cruise_alt_m = payload.cruise_alt
        row_spacing_m = g.row_spacing_m
        agl_m = g.agl_m
        if profile is not None:
            recommended = _compute_photogrammetry_spacing(profile)
            cruise_alt_m = float(profile.altitude_m)
            agl_m = float(profile.altitude_m)
            row_spacing_m = recommended["cross_track_m"]

            # If trigger strategy under-samples along-track spacing, reject early.
            if recommended["effective_trigger_spacing_m"] > recommended["along_track_m"] * 1.15:
                raise ValueError(
                    "Trigger cadence is too sparse for requested front overlap. "
                    "Reduce trigger distance/interval or speed."
                )

        # Convert [[lon, lat], …] → [(lon, lat), …] tuples for GridMission.
        poly = [tuple(pt) for pt in g.field_polygon_lonlat]
        mission = GridMission(
            cruise_alt_m=cruise_alt_m,
            field_polygon_lonlat=poly,
            row_spacing_m=row_spacing_m,
            grid_angle_deg=g.grid_angle_deg,
            slope_aware=g.slope_aware,
            safety_inset_m=g.safety_inset_m,
            terrain_follow=g.terrain_follow,
            agl_m=agl_m,
            pattern_mode=g.pattern_mode,
            crosshatch_angle_offset_deg=g.crosshatch_angle_offset_deg,
            start_corner=g.start_corner,
            lane_strategy=g.lane_strategy,
            row_stride=g.row_stride,
            row_phase_m=g.row_phase_m,
        )
        return mission, len(poly)

    raise ValueError(f"Unknown mission_type: {payload.mission_type!r}")


def _compute_photogrammetry_spacing(profile: PhotogrammetryMissionProfile) -> dict:
    """Derive survey spacing from capture profile."""
    front = float(profile.front_overlap_pct) / 100.0
    side = float(profile.side_overlap_pct) / 100.0
    altitude = float(profile.altitude_m)

    footprint_w = 2.0 * altitude * math.tan(math.radians(profile.camera.fov_h_deg / 2.0))
    footprint_h = 2.0 * altitude * math.tan(math.radians(profile.camera.fov_v_deg / 2.0))

    along_track_m = max(0.5, footprint_h * (1.0 - front))
    cross_track_m = max(0.5, footprint_w * (1.0 - side))

    trigger = profile.trigger
    if isinstance(trigger, MissionProfileTriggerDistance):
        effective_trigger_spacing = float(trigger.distance_m)
    else:
        effective_trigger_spacing = float(profile.speed_mps) * float(trigger.interval_s)

    return {
        "along_track_m": along_track_m,
        "cross_track_m": cross_track_m,
        "effective_trigger_spacing_m": effective_trigger_spacing,
    }


# ---------------------------------------------------------------------------
# Generic mission executor (thin wrapper — no type coupling)
# ---------------------------------------------------------------------------

async def execute_mission(
        orch: Any,
        mission: Any,       # Any object with .execute(orch, alt=…) method
        cruise_alt: float,
        mission_name: str,
) -> None:
    """Run any mission that implements .execute(orch, *, alt)."""
    try:
        await mission.execute(orch, alt=cruise_alt)
        logger.info("✅ Mission '%s' completed successfully", mission_name)
        print(f"✅ Mission '{mission_name}' completed successfully")
    except Exception as exc:
        logger.exception("❌ Mission '%s' failed", mission_name)
        print(f"❌ Mission '{mission_name}' failed: {exc}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/missions", response_model=MissionCreateOut)
async def create_mission(
        payload: MissionCreateIn,
        db: Session = Depends(get_db),
        user=Depends(require_user),
):
    """Create and start a mission — returns flight_id for WebSocket tracking.

    Supported mission types
    -----------------------
    ``"waypoints"``  – fly an ordered list of lat/lon/alt coordinates.
    ``"grid"``       – auto-generate a lawnmower survey over a field polygon.
    """
    try:
        mission, wps_count = _build_mission(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client_flight_id = f"flight_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    orch = await get_orchestrator()
    active_task = getattr(orch, "_active_mission_task", None)
    if active_task is not None and not active_task.done():
        raise HTTPException(
            status_code=409,
            detail="Another mission is already running. Wait for it to complete before starting a new one.",
        )

    orch.current_mission_name = payload.name
    orch.current_client_flight_id = client_flight_id

    task = asyncio.create_task(
        execute_mission(orch, mission, payload.cruise_alt, payload.name)
    )
    orch._active_mission_task = task

    def _clear_active_mission_task(done_task: asyncio.Task) -> None:
        if getattr(orch, "_active_mission_task", None) is done_task:
            orch._active_mission_task = None

    task.add_done_callback(_clear_active_mission_task)

    return MissionCreateOut(
        flight_id=client_flight_id,
        status="executing",
        mission_name=payload.name,
        mission_type=payload.mission_type.value,
        waypoints_count=wps_count,
    )


@router.get("/flight/status")
async def get_flight_status():
    """Current flight status + telemetry summary."""
    try:
        orch = await get_orchestrator()
        flight_id = str(orch._flight_id) if getattr(orch, "_flight_id", None) else None
        mission_name = getattr(orch, "current_mission_name", "Unknown")

        position = telemetry_manager.last_telemetry.get("position", {})
        has_position = bool(position.get("lat") or position.get("lon"))

        return {
            "flight_id": flight_id,
            "mission_name": mission_name,
            "telemetry": {
                "running": telemetry_manager._running,
                "active_connections": len(telemetry_manager.active_connections),
                "has_position_data": has_position,
                "last_update": telemetry_manager.last_telemetry.get("timestamp", 0),
                "position": position,
            },
            "orchestrator": {
                "ready": orch is not None,
                "has_drone": getattr(orch, "drone", None) is not None,
                "drone_connected": (
                        hasattr(orch, "drone")
                        and getattr(orch, "drone", None) is not None
                        and getattr(getattr(orch, "drone", None), "vehicle", None) is not None
                ),
            },
        }
    except Exception as exc:
        logger.exception("get_flight_status failed")
        return {
            "error": str(exc),
            "telemetry": {
                "running": telemetry_manager._running,
                "active_connections": len(telemetry_manager.active_connections),
            },
        }


@router.get("/drone/position")
async def get_drone_position():
    """Current drone position from telemetry cache."""
    position = telemetry_manager.last_telemetry.get("position", {})
    lat = position.get("lat", 0)
    lon = position.get("lon", 0)
    return {
        "has_position": lat != 0 or lon != 0,
        "lat": lat,
        "lng": lon,
        "alt": position.get("alt", 0),
        "relative_alt": position.get("relative_alt", 0),
        "timestamp": telemetry_manager.last_telemetry.get("timestamp", 0),
    }


@router.post("/telemetry/start")
async def start_telemetry():
    if telemetry_manager._running:
        return {"status": "already_running", "message": "Telemetry already running"}
    try:
        telemetry_manager.start_telemetry_stream()
        return {"status": "started", "message": "Telemetry stream started"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start telemetry: {exc}") from exc


@router.post("/telemetry/stop")
async def stop_telemetry():
    if not telemetry_manager._running:
        return {"status": "already_stopped", "message": "Telemetry already stopped"}
    try:
        telemetry_manager.stop_telemetry_stream()
        return {"status": "stopped", "message": "Telemetry stream stopped"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stop telemetry: {exc}") from exc


# ---------------------------------------------------------------------------
# Grid preview endpoint (no drone required – useful for UI previews)
# ---------------------------------------------------------------------------

class GridPreviewIn(BaseModel):
    field_polygon_lonlat: List[List[float]] = Field(..., min_length=3)
    row_spacing_m: float = Field(default=7.5, gt=0, le=200)
    grid_angle_deg: Optional[float] = Field(default=None, ge=0, lt=180)
    safety_inset_m: float = Field(default=1.5, ge=0)
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = Field(default=90.0, gt=0, lt=180)
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    row_stride: int = Field(default=1, ge=1, le=20)
    row_phase_m: float = Field(default=0.0, ge=0.0, le=500.0)


class GridPreviewOut(BaseModel):
    waypoints: List[dict]
    work_leg_mask: List[bool]
    angle_deg: float
    spacing_m: float
    stats: dict


@router.post("/missions/grid-preview", response_model=GridPreviewOut)
async def preview_grid(payload: GridPreviewIn):
    """Compute and return a grid plan without executing a flight.

    The frontend uses this to draw the lawnmower overlay on the map
    before the user hits 'Start Flight Plan'.
    """
    from backend.flight.missions.grid_mission import (
        GridPlanner,
        combine_grid_plans,
        _validate_plan_limits,
    )

    try:
        poly = [tuple(pt) for pt in payload.field_polygon_lonlat]
        angle = payload.grid_angle_deg if payload.grid_angle_deg is not None else 0.0
        primary = GridPlanner.generate(
            poly,
            spacing_m=payload.row_spacing_m,
            angle_deg=angle,
            inset_m=payload.safety_inset_m,
            start_corner=payload.start_corner,
            lane_strategy=payload.lane_strategy,
            row_stride=payload.row_stride,
            row_phase_m=payload.row_phase_m,
        )
        plans = [primary]
        if payload.pattern_mode == "crosshatch":
            angle2 = (angle + payload.crosshatch_angle_offset_deg) % 180.0
            if abs(angle2 - angle) > 1e-6:
                secondary = GridPlanner.generate(
                    poly,
                    spacing_m=payload.row_spacing_m,
                    angle_deg=angle2,
                    inset_m=payload.safety_inset_m,
                    start_corner=payload.start_corner,
                    lane_strategy=payload.lane_strategy,
                    row_stride=payload.row_stride,
                    row_phase_m=payload.row_phase_m,
                )
                plans.append(secondary)
        plan = combine_grid_plans(plans, poly_lonlat=poly, pattern_mode=payload.pattern_mode)
        _validate_plan_limits(plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GridPreviewOut(
        waypoints=[{"lat": w.lat, "lon": w.lon} for w in plan.waypoints],
        work_leg_mask=plan.work_leg_mask,
        angle_deg=plan.angle_deg,
        spacing_m=plan.spacing_m,
        stats=plan.stats,
    )
