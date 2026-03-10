from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Literal, Optional, Union, Annotated
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
from backend.auth.deps import require_user
from backend.db.models import FlightStatus
from backend.drone.models import Coordinate
from backend.drone.drone_base import MissionAbortRequested
from backend.flight.missions.grid_mission import GridMission
from backend.flight.missions.private_patrol import (
    EventTriggeredPatrolMission,
    PATROL_AI_TASKS,
    GridSurveillanceMission,
    PrivatePatrolMission,
    WaypointPatrolMission,
    estimate_camera_trigger_distance_m,
    generate_event_triggered_patrol_plan,
    generate_grid_surveillance_plan,
    generate_private_patrol_plan,
    generate_waypoint_patrol_plan,
    normalize_ai_tasks,
    normalize_patrol_direction,
    normalize_trigger_type,
    private_patrol_task_catalog,
    repeat_patrol_loops,
    trigger_action_profile,
)
from backend.flight.missions.photogrammetry_mission import (
    PhotogrammetryMission as FlightPhotogrammetryMission,
)
from backend.flight.preflight_check.schemas import PreflightReport
from backend.flight.missions.waypoints_mission import WaypointsMission
from backend.main import _build_orchestrator
from backend.messaging.websocket import telemetry_manager
from backend.flight.missions.schemas import MissionType, Waypoint
from backend.services.patrol.mission_runtime_store import (
    MissionRuntimeRecord,
    MissionCommandAuditRecord,
    mission_runtime_store,
)


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/tasks", tags=["tasks"])

_BOOL_TRUE_TOKENS = {"1", "true", "yes", "on"}
PREFLIGHT_RUN_TTL_SECONDS = max(
    60, int(os.getenv("PREFLIGHT_RUN_TTL_SECONDS", "900"))
)
REQUIRE_PREFLIGHT_RUN_BEFORE_MISSION = (
    os.getenv("REQUIRE_PREFLIGHT_RUN_BEFORE_MISSION", "0").strip().lower()
    in _BOOL_TRUE_TOKENS
)
ALLOW_WARN_PREFLIGHT_START = (
    os.getenv("ALLOW_WARN_PREFLIGHT_START", "1").strip().lower()
    in _BOOL_TRUE_TOKENS
)


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


PatrolTaskType = Literal[
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


class PrivatePatrolMissionParams(BaseModel):
    """Parameters for private patrol missions."""

    task_type: Literal[
        "perimeter_patrol",
        "waypoint_patrol",
        "grid_surveillance",
        "event_triggered_patrol",
    ] = "perimeter_patrol"
    property_polygon_lonlat: Optional[List[List[float]]] = Field(
        default=None,
        min_length=3,
        description="Perimeter/Grid mode: property polygon ring as [[lon, lat], ...]",
    )
    key_points_lonlat: Optional[List[List[float]]] = Field(
        default=None,
        min_length=2,
        description="Waypoint mode: ordered key points as [[lon, lat], ...]",
    )
    path_offset_m: float = Field(default=15.0, ge=0.0, le=120.0)
    direction: Literal["clockwise", "counterclockwise"] = "clockwise"
    patrol_loops: int = Field(default=1, ge=1, le=200)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    camera_angle_deg: float = Field(default=35.0, ge=0.0, le=90.0)
    camera_overlap_pct: float = Field(default=50.0, ge=0.0, le=95.0)
    max_segment_length_m: float = Field(default=20.0, gt=1.0, le=300.0)
    hover_time_s: float = Field(default=15.0, ge=1.0, le=300.0)
    camera_scan_yaw_deg: float = Field(default=360.0, ge=0.0, le=360.0)
    zoom_capture: bool = True
    return_to_start: bool = True
    grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    grid_angle_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    safety_inset_m: float = Field(default=2.0, ge=0.0, le=100.0)
    trigger_type: PatrolTriggerType = "fence_alarm"
    trigger_event_location_lonlat: Optional[List[float]] = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Event task: trigger location as [lon, lat]",
    )
    target_label: Optional[str] = Field(default=None, max_length=120)
    verification_loiter_s: float = Field(default=45.0, ge=0.0, le=600.0)
    verification_radius_m: float = Field(default=18.0, ge=0.0, le=150.0)
    track_target: bool = True
    auto_stream_video: bool = True
    ai_tasks: List[PatrolTaskType] = Field(default_factory=lambda: list(PATROL_AI_TASKS))

    @model_validator(mode="after")
    def _validate_by_task(self) -> "PrivatePatrolMissionParams":
        if self.task_type in {"perimeter_patrol", "grid_surveillance"}:
            if not self.property_polygon_lonlat or len(self.property_polygon_lonlat) < 3:
                raise ValueError(
                    f"task_type='{self.task_type}' requires property_polygon_lonlat with at least 3 coordinate pairs."
                )
        elif self.task_type == "waypoint_patrol":
            if not self.key_points_lonlat or len(self.key_points_lonlat) < 2:
                raise ValueError(
                    "task_type='waypoint_patrol' requires key_points_lonlat with at least 2 coordinate pairs."
                )
        elif self.task_type == "event_triggered_patrol":
            _ = normalize_trigger_type(self.trigger_type)
            has_event_loc = bool(self.trigger_event_location_lonlat and len(self.trigger_event_location_lonlat) == 2)
            if self.trigger_type == "night_schedule":
                if not has_event_loc and not (self.property_polygon_lonlat and len(self.property_polygon_lonlat) >= 3):
                    raise ValueError(
                        "task_type='event_triggered_patrol' with trigger_type='night_schedule' "
                        "requires trigger_event_location_lonlat or property_polygon_lonlat."
                    )
            elif not has_event_loc:
                raise ValueError(
                    "task_type='event_triggered_patrol' requires trigger_event_location_lonlat=[lon, lat]."
                )
        return self


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
    min_spacing_m: float = Field(default=0.5, gt=0.0, le=10.0)
    speed_mps: float = Field(default=3.0, gt=0.1, le=20.0)
    trigger: MissionProfileTrigger = Field(default_factory=MissionProfileTriggerDistance)
    accuracy: Literal["standard_gnss", "rtk_ppk"] = "rtk_ppk"
    camera: MissionProfileCamera = Field(default_factory=MissionProfileCamera)


class MissionCreateIn(BaseModel):
    """
    Unified mission creation payload.

    For `mission_type = "waypoints"`: supply `waypoints` (≥ 2).
    For `mission_type = "grid"`:     supply `grid` params with polygon.
    For `mission_type = "perimeter_patrol"` / `"private_patrol"`:
        supply `private_patrol` params:
          - perimeter task uses `property_polygon_lonlat`
          - waypoint task uses `key_points_lonlat`
          - grid task uses `property_polygon_lonlat` + grid parameters
    """
    name: str = Field(default="mission", min_length=1, max_length=120)
    cruise_alt: float = Field(default=30.0, gt=0, le=500)
    mission_type: MissionType = MissionType.WAYPOINT

    # Waypoints mission data
    waypoints: Optional[List[Waypoint]] = None

    # Grid mission data
    grid: Optional[GridMissionParams] = None
    private_patrol: Optional[PrivatePatrolMissionParams] = None
    mission_profile: Optional[PhotogrammetryMissionProfile] = None
    preflight_run_id: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=128,
        description=(
            "Optional preflight run token from POST /tasks/preflight/run. "
            "When provided, mission start validates that token against this payload."
        ),
    )

    @model_validator(mode="after")
    def _check_payload(self) -> "MissionCreateIn":
        if self.mission_type == MissionType.WAYPOINT:
            if not self.waypoints or len(self.waypoints) < 2:
                raise ValueError(
                    "mission_type='waypoints' requires at least 2 waypoints."
                )
        elif self.mission_type in {MissionType.GRID, MissionType.PHOTOGRAMMETRY}:
            if self.grid is None:
                raise ValueError(
                    "mission_type requires a 'grid' object with field_polygon_lonlat."
                )
            if len(self.grid.field_polygon_lonlat) < 3:
                raise ValueError(
                    "field_polygon_lonlat must have at least 3 coordinate pairs."
                )
        elif self.mission_type in {MissionType.PERIMETER_PATROL, MissionType.PRIVATE_PATROL}:
            if self.private_patrol is None:
                raise ValueError(
                    "mission_type='perimeter_patrol' requires a 'private_patrol' object."
                )
        if (
            self.mission_profile is not None
            and self.mission_type not in {MissionType.GRID, MissionType.PHOTOGRAMMETRY}
        ):
            raise ValueError(
                "mission_profile is supported only for mission_type='grid' or 'photogrammetry'."
            )
        return self


class MissionCreateOut(BaseModel):
    flight_id: str
    status: str
    mission_name: str
    mission_type: str
    waypoints_count: int
    preflight_run_id: Optional[str] = None


class MissionRuntimeOut(BaseModel):
    flight_id: str
    mission_name: str
    mission_type: str
    mission_task_type: Optional[str] = None
    state: str
    created_at: float
    updated_at: float
    preflight_run_id: Optional[str] = None
    db_flight_id: Optional[str] = None
    last_error: Optional[str] = None


class MissionCommandIn(BaseModel):
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="Idempotency key. Can also be provided via Idempotency-Key header.",
    )
    reason: Optional[str] = Field(default=None, max_length=240)


class MissionCommandOut(BaseModel):
    flight_id: str
    command_id: str
    command: str
    idempotency_key: str
    state_before: str
    state_after: str
    accepted: bool
    message: str
    requested_at: float


class MissionCommandAuditOut(BaseModel):
    command_id: str
    command: str
    idempotency_key: str
    requested_by_user_id: int
    requested_at: float
    state_before: str
    state_after: str
    accepted: bool
    message: str
    reason: Optional[str] = None


class PreflightRunOut(BaseModel):
    preflight_run_id: str
    mission_fingerprint: str
    overall_status: str
    can_start_mission: bool
    created_at: float
    expires_at: float
    report: PreflightReport


@dataclass
class _PreflightRunRecord:
    run_id: str
    user_id: int
    mission_fingerprint: str
    overall_status: str
    created_at: float
    expires_at: float
    report: dict


MissionLifecycleState = Literal[
    "queued",
    "running",
    "paused",
    "aborted",
    "completed",
    "failed",
]
MissionCommand = Literal["pause", "resume", "abort"]
TERMINAL_MISSION_STATES = {"aborted", "completed", "failed"}


@dataclass
class _MissionCommandAudit:
    command_id: str
    command: MissionCommand
    idempotency_key: str
    requested_by_user_id: int
    requested_at: float
    state_before: MissionLifecycleState
    state_after: MissionLifecycleState
    accepted: bool
    message: str
    reason: Optional[str] = None


@dataclass
class _MissionRuntimeRecord:
    client_flight_id: str
    user_id: int
    mission_name: str
    mission_type: str
    mission_task_type: Optional[str]
    private_patrol_task_type: Optional[str]
    preflight_run_id: Optional[str]
    state: MissionLifecycleState
    created_at: float
    updated_at: float
    db_flight_id: Optional[int] = None
    last_error: Optional[str] = None
    private_patrol_trigger_type: Optional[str] = None
    private_patrol_target_label: Optional[str] = None
    command_audit: List[_MissionCommandAudit] = field(default_factory=list)
    idempotency_results: dict[str, dict] = field(default_factory=dict)
    private_patrol_ai_tasks: List[str] = field(default_factory=list)



_preflight_runs_lock = threading.Lock()
_preflight_runs: dict[str, _PreflightRunRecord] = {}


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
# Mission runtime lifecycle store
# ---------------------------------------------------------------------------

MISSION_RUNTIME_TTL_SECONDS = max(
    600,
    int(os.getenv("MISSION_RUNTIME_TTL_SECONDS", "86400")),
)
MISSION_RUNTIME_MAX_HISTORY = max(
    20,
    int(os.getenv("MISSION_RUNTIME_MAX_HISTORY", "200")),
)

_mission_runtime_lock = asyncio.Lock()
_active_mission_runtime_id: Optional[str] = None
_mission_runtimes: dict[str, _MissionRuntimeRecord] = {}


def _is_terminal_state(state: str) -> bool:
    return str(state).lower() in TERMINAL_MISSION_STATES


def _db_status_for_runtime_state(state: MissionLifecycleState) -> FlightStatus:
    if state == "running":
        return FlightStatus.ACTIVE
    if state == "paused":
        return FlightStatus.PAUSED
    if state == "aborted":
        return FlightStatus.INTERRUPTED
    if state == "completed":
        return FlightStatus.COMPLETED
    return FlightStatus.FAILED


def _runtime_to_out(rec: _MissionRuntimeRecord) -> MissionRuntimeOut:
    return MissionRuntimeOut(
        flight_id=rec.client_flight_id,
        mission_name=rec.mission_name,
        mission_type=rec.mission_type,
        mission_task_type=(rec.private_patrol_task_type or rec.mission_task_type or None),
        state=rec.state,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        preflight_run_id=rec.preflight_run_id,
        db_flight_id=str(rec.db_flight_id) if rec.db_flight_id is not None else None,
        last_error=rec.last_error,
    )


def _audit_to_out(audit: _MissionCommandAudit) -> MissionCommandAuditOut:
    return MissionCommandAuditOut(
        command_id=audit.command_id,
        command=audit.command,
        idempotency_key=audit.idempotency_key,
        requested_by_user_id=audit.requested_by_user_id,
        requested_at=audit.requested_at,
        state_before=audit.state_before,
        state_after=audit.state_after,
        accepted=audit.accepted,
        message=audit.message,
        reason=audit.reason,
    )


def _cleanup_stale_mission_runtimes(now_s: float) -> None:
    if len(_mission_runtimes) <= MISSION_RUNTIME_MAX_HISTORY:
        return
    removable = sorted(
        _mission_runtimes.values(),
        key=lambda rec: rec.updated_at,
    )
    for rec in removable:
        if len(_mission_runtimes) <= MISSION_RUNTIME_MAX_HISTORY:
            break
        if _active_mission_runtime_id == rec.client_flight_id:
            continue
        age = now_s - rec.updated_at
        if age < MISSION_RUNTIME_TTL_SECONDS and not _is_terminal_state(rec.state):
            continue
        _mission_runtimes.pop(rec.client_flight_id, None)


def _allowed_command_transition(
    current: MissionLifecycleState,
    command: MissionCommand,
) -> Optional[MissionLifecycleState]:
    transitions: dict[tuple[MissionLifecycleState, MissionCommand], MissionLifecycleState] = {
        ("queued", "abort"): "aborted",
        ("running", "pause"): "paused",
        ("running", "abort"): "aborted",
        ("paused", "resume"): "running",
        ("paused", "abort"): "aborted",
    }
    return transitions.get((current, command))


def _record_command_audit(
    runtime: _MissionRuntimeRecord,
    audit: _MissionCommandAudit,
    response_payload: dict,
) -> None:
    runtime.command_audit.append(audit)
    runtime.idempotency_results[audit.idempotency_key] = response_payload
    runtime.updated_at = max(runtime.updated_at, audit.requested_at)
    if len(runtime.command_audit) > 400:
        runtime.command_audit = runtime.command_audit[-400:]


async def _sync_runtime_flight_id_from_orchestrator(
    runtime: _MissionRuntimeRecord,
    orch: Any,
) -> None:
    if runtime.db_flight_id is not None:
        return
    raw = getattr(orch, "_flight_id", None)
    if raw is None:
        return
    try:
        runtime.db_flight_id = int(raw)
    except Exception:
        runtime.db_flight_id = None


async def _set_runtime_state(
    runtime_id: str,
    *,
    state: MissionLifecycleState,
    error: Optional[str] = None,
) -> None:
    global _active_mission_runtime_id
    now = time.time()
    async with _mission_runtime_lock:
        runtime = _mission_runtimes.get(runtime_id)
        if runtime is None:
            return
        runtime.state = state
        runtime.updated_at = now
        if error:
            runtime.last_error = error
        if _active_mission_runtime_id == runtime_id and _is_terminal_state(state):
            # keep record for audit/history; just clear active pointer
            _active_mission_runtime_id = None
        _cleanup_stale_mission_runtimes(now)

# ---------------------------------------------------------------------------
# Preflight store helpers
# ---------------------------------------------------------------------------

def _cleanup_expired_preflight_runs(now_s: Optional[float] = None) -> None:
    now = time.time() if now_s is None else now_s
    expired = [run_id for run_id, rec in _preflight_runs.items() if rec.expires_at <= now]
    for run_id in expired:
        _preflight_runs.pop(run_id, None)


def _mission_fingerprint(payload: MissionCreateIn) -> str:
    canonical = payload.model_dump(mode="json", exclude={"preflight_run_id"})
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _store_preflight_run(
    *,
    user_id: int,
    mission_fingerprint: str,
    report: PreflightReport,
) -> _PreflightRunRecord:
    now = time.time()
    run_id = f"pf_{int(now)}_{uuid.uuid4().hex[:10]}"
    rec = _PreflightRunRecord(
        run_id=run_id,
        user_id=user_id,
        mission_fingerprint=mission_fingerprint,
        overall_status=str(report.overall_status),
        created_at=now,
        expires_at=now + PREFLIGHT_RUN_TTL_SECONDS,
        report=report.model_dump(mode="json"),
    )
    with _preflight_runs_lock:
        _cleanup_expired_preflight_runs(now)
        _preflight_runs[run_id] = rec
    return rec


def _get_preflight_run(run_id: str) -> Optional[_PreflightRunRecord]:
    with _preflight_runs_lock:
        _cleanup_expired_preflight_runs()
        return _preflight_runs.get(run_id)


def _preflight_allows_start(overall_status: str) -> bool:
    normalized = str(overall_status).upper()
    if normalized == "PASS":
        return True
    if normalized == "WARN":
        return ALLOW_WARN_PREFLIGHT_START
    return False


def _preflight_record_out(rec: _PreflightRunRecord) -> PreflightRunOut:
    return PreflightRunOut(
        preflight_run_id=rec.run_id,
        mission_fingerprint=rec.mission_fingerprint,
        overall_status=rec.overall_status,
        can_start_mission=_preflight_allows_start(rec.overall_status),
        created_at=rec.created_at,
        expires_at=rec.expires_at,
        report=PreflightReport.model_validate(rec.report),
    )


async def _ensure_drone_ready_for_preflight(orch: Any) -> None:
    try:
        await asyncio.to_thread(orch.drone.get_telemetry)
        return
    except Exception:
        logger.info("Telemetry unavailable, attempting to connect drone for preflight run")

    await asyncio.to_thread(orch.drone.connect)
    # Ensure connect actually yielded a readable state.
    await asyncio.to_thread(orch.drone.get_telemetry)


def _polygon_centroid_lonlat(polygon_lonlat: List[tuple[float, float]]) -> tuple[float, float]:
    if len(polygon_lonlat) < 3:
        raise ValueError("polygon must have at least 3 points")
    pts = list(polygon_lonlat)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    lon = sum(float(p[0]) for p in pts) / len(pts)
    lat = sum(float(p[1]) for p in pts) / len(pts)
    return lon, lat


def _resolve_trigger_event_location(
    *,
    trigger_type: str,
    trigger_event_location_lonlat: Optional[List[float]],
    property_polygon_lonlat: Optional[List[List[float]]],
) -> tuple[float, float]:
    normalized_trigger = normalize_trigger_type(trigger_type)
    if trigger_event_location_lonlat and len(trigger_event_location_lonlat) >= 2:
        lon = float(trigger_event_location_lonlat[0])
        lat = float(trigger_event_location_lonlat[1])
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("trigger_event_location_lonlat must be valid [lon, lat]")
        return lon, lat

    if normalized_trigger == "night_schedule":
        polygon = [tuple(pt) for pt in (property_polygon_lonlat or [])]
        if len(polygon) >= 3:
            return _polygon_centroid_lonlat(polygon)

    raise ValueError(
        "Unable to resolve event location. Provide trigger_event_location_lonlat "
        "or property_polygon_lonlat for night_schedule."
    )


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

    if payload.mission_type in {MissionType.GRID, MissionType.PHOTOGRAMMETRY}:
        g = payload.grid  # validated non-None by model_validator
        profile = payload.mission_profile
        if payload.mission_type == MissionType.PHOTOGRAMMETRY and profile is None:
            profile = PhotogrammetryMissionProfile()

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
        if profile is not None:
            trigger = profile.trigger
            trigger_mode: Literal["distance", "time"]
            trigger_distance_m = 0.0
            trigger_interval_s = 0.0
            if isinstance(trigger, MissionProfileTriggerDistance):
                trigger_mode = "distance"
                trigger_distance_m = float(trigger.distance_m)
            else:
                trigger_mode = "time"
                trigger_interval_s = float(trigger.interval_s)

            mission = FlightPhotogrammetryMission(
                polygon_lonlat=poly,
                altitude_agl=float(profile.altitude_m),
                fov_h=float(profile.camera.fov_h_deg),
                fov_v=float(profile.camera.fov_v_deg),
                front_overlap=float(profile.front_overlap_pct) / 100.0,
                side_overlap=float(profile.side_overlap_pct) / 100.0,
                min_spacing_m=float(profile.min_spacing_m),
                heading_deg=float(g.grid_angle_deg or 0.0),
                speed_mps=float(profile.speed_mps),
                trigger_mode=trigger_mode,
                trigger_distance_m=trigger_distance_m
                or max(float(profile.min_spacing_m), recommended["along_track_m"]),
                trigger_interval_s=trigger_interval_s
                or max(0.2, recommended["along_track_m"] / max(0.1, float(profile.speed_mps))),
                terrain_follow=bool(g.terrain_follow),
                terrain_target_agl_m=float(agl_m) if g.terrain_follow else None,
            )
            return mission, len(poly)

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

    if payload.mission_type in {MissionType.PERIMETER_PATROL, MissionType.PRIVATE_PATROL}:
        patrol = payload.private_patrol  # validated non-None by model_validator
        ai_tasks = normalize_ai_tasks(patrol.ai_tasks)
        if patrol.task_type == "event_triggered_patrol":
            event_lon, event_lat = _resolve_trigger_event_location(
                trigger_type=patrol.trigger_type,
                trigger_event_location_lonlat=patrol.trigger_event_location_lonlat,
                property_polygon_lonlat=patrol.property_polygon_lonlat,
            )
            mission = EventTriggeredPatrolMission(
                trigger_type=normalize_trigger_type(patrol.trigger_type),
                event_location_lonlat=(float(event_lon), float(event_lat)),
                altitude_agl=float(payload.cruise_alt),
                speed_mps=float(patrol.speed_mps),
                verification_loiter_s=float(patrol.verification_loiter_s),
                verification_radius_m=float(patrol.verification_radius_m),
                track_target=bool(patrol.track_target),
                auto_stream_video=bool(patrol.auto_stream_video),
                target_label=patrol.target_label,
                ai_tasks=ai_tasks,
            )
            return mission, len(mission.get_waypoints())

        if patrol.task_type == "grid_surveillance":
            polygon = [tuple(pt) for pt in (patrol.property_polygon_lonlat or [])]
            mission = GridSurveillanceMission(
                polygon_lonlat=polygon,
                altitude_agl=float(payload.cruise_alt),
                speed_mps=float(patrol.speed_mps),
                grid_spacing_m=float(patrol.grid_spacing_m),
                grid_angle_deg=float(patrol.grid_angle_deg),
                safety_inset_m=float(patrol.safety_inset_m),
                ai_tasks=ai_tasks,
            )
            return mission, len(mission.get_waypoints())

        if patrol.task_type == "waypoint_patrol":
            key_points = [tuple(pt) for pt in (patrol.key_points_lonlat or [])]
            mission = WaypointPatrolMission(
                key_points_lonlat=key_points,
                altitude_agl=float(payload.cruise_alt),
                speed_mps=float(patrol.speed_mps),
                hover_time_s=float(patrol.hover_time_s),
                camera_scan_yaw_deg=float(patrol.camera_scan_yaw_deg),
                zoom_capture=bool(patrol.zoom_capture),
                return_to_start=bool(patrol.return_to_start),
                ai_tasks=ai_tasks,
            )
            return mission, len(mission.get_waypoints())

        polygon = [tuple(pt) for pt in (patrol.property_polygon_lonlat or [])]
        direction = normalize_patrol_direction(patrol.direction)
        mission = PrivatePatrolMission(
            polygon_lonlat=polygon,
            altitude_agl=float(payload.cruise_alt),
            speed_mps=float(patrol.speed_mps),
            patrol_direction=direction,
            path_offset_m=float(patrol.path_offset_m),
            loop_count=int(patrol.patrol_loops),
            camera_angle_deg=float(patrol.camera_angle_deg),
            camera_overlap_pct=float(patrol.camera_overlap_pct),
            max_segment_length_m=float(patrol.max_segment_length_m),
            ai_tasks=ai_tasks,
        )
        return mission, len(mission.get_waypoints())

    raise ValueError(f"Unknown mission_type: {payload.mission_type!r}")


def _compute_photogrammetry_spacing(profile: PhotogrammetryMissionProfile) -> dict:
    """Derive survey spacing from capture profile."""
    front = float(profile.front_overlap_pct) / 100.0
    side = float(profile.side_overlap_pct) / 100.0
    altitude = float(profile.altitude_m)

    footprint_w = 2.0 * altitude * math.tan(math.radians(profile.camera.fov_h_deg / 2.0))
    footprint_h = 2.0 * altitude * math.tan(math.radians(profile.camera.fov_v_deg / 2.0))

    spacing_floor = max(0.0, float(profile.min_spacing_m))
    along_track_m = max(spacing_floor, footprint_h * (1.0 - front))
    cross_track_m = max(spacing_floor, footprint_w * (1.0 - side))

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
        runtime_id: str,
) -> None:
    """Run any mission that implements .execute(orch, *, alt)."""
    global _active_mission_runtime_id
    reconcile_db_flight_id: Optional[int] = None
    reconcile_db_status: Optional[FlightStatus] = None
    reconcile_note: str = ""
    await _set_runtime_state(runtime_id, state="running")
    try:
        await mission.execute(orch, alt=cruise_alt)
        async with _mission_runtime_lock:
            runtime = _mission_runtimes.get(runtime_id)
            if runtime is not None:
                await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
                if runtime.state != "aborted":
                    runtime.state = "completed"
                    runtime.updated_at = time.time()
                if _active_mission_runtime_id == runtime_id and _is_terminal_state(runtime.state):
                    _active_mission_runtime_id = None
        logger.info("✅ Mission '%s' completed successfully", mission_name)
        print(f"✅ Mission '{mission_name}' completed successfully")
    except MissionAbortRequested as exc:
        await _set_runtime_state(runtime_id, state="aborted", error=str(exc))
        logger.warning("🛑 Mission '%s' aborted: %s", mission_name, exc)
    except asyncio.CancelledError:
        async with _mission_runtime_lock:
            runtime = _mission_runtimes.get(runtime_id)
            aborted = runtime is not None and runtime.state == "aborted"
        if not aborted:
            await _set_runtime_state(
                runtime_id,
                state="failed",
                error="Mission task cancelled unexpectedly",
            )
            logger.exception("❌ Mission '%s' was cancelled unexpectedly", mission_name)
        else:
            logger.info("Mission '%s' cancelled after abort command", mission_name)
    except Exception as exc:
        async with _mission_runtime_lock:
            runtime = _mission_runtimes.get(runtime_id)
            already_aborted = runtime is not None and runtime.state == "aborted"
        if not already_aborted:
            await _set_runtime_state(runtime_id, state="failed", error=str(exc))
        logger.exception("❌ Mission '%s' failed", mission_name)
        print(f"❌ Mission '{mission_name}' failed: {exc}")
    finally:
        async with _mission_runtime_lock:
            runtime = _mission_runtimes.get(runtime_id)
            if runtime is not None:
                await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
                runtime.updated_at = time.time()
                if _active_mission_runtime_id == runtime_id and _is_terminal_state(runtime.state):
                    _active_mission_runtime_id = None
                if runtime.db_flight_id is not None and _is_terminal_state(runtime.state):
                    reconcile_db_flight_id = runtime.db_flight_id
                    reconcile_db_status = _db_status_for_runtime_state(runtime.state)
                    reconcile_note = (
                        f"Mission {runtime.state}: {runtime.last_error}"
                        if runtime.last_error
                        else f"Mission {runtime.state}"
                    )

        if reconcile_db_flight_id is not None and reconcile_db_status is not None:
            safe_note = reconcile_note[:250] if reconcile_note else f"Mission {reconcile_db_status.value}"
            try:
                await orch.repo.finish_flight_if_in_progress(
                    reconcile_db_flight_id,
                    status=reconcile_db_status,
                    note=safe_note,
                )
            except Exception:
                logger.exception(
                    "Failed reconciling terminal flight status to %s for db_flight_id=%s",
                    reconcile_db_status.value,
                    reconcile_db_flight_id,
                )


async def _get_runtime_for_user(
    flight_id: str,
    *,
    user_id: int,
) -> _MissionRuntimeRecord:
    async with _mission_runtime_lock:
        runtime = _mission_runtimes.get(flight_id)
        if runtime is None or runtime.user_id != int(user_id):
            raise HTTPException(status_code=404, detail="Mission not found")
        return runtime


def _resolve_idempotency_key(
    payload_key: Optional[str],
    header_key: Optional[str],
) -> str:
    payload = (payload_key or "").strip()
    header = (header_key or "").strip()
    if payload and header and payload != header:
        raise HTTPException(
            status_code=409,
            detail="Idempotency key mismatch between body and Idempotency-Key header.",
        )

    key = payload or header
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency key required (body.idempotency_key or Idempotency-Key header).",
        )
    if len(key) < 8 or len(key) > 128:
        raise HTTPException(status_code=400, detail="Invalid idempotency key length")
    return key


async def _persist_state_change_event(
    orch: Any,
    runtime: _MissionRuntimeRecord,
    *,
    event_type: str,
    data: dict,
) -> None:
    if runtime.db_flight_id is None:
        return
    try:
        await orch.repo.add_event(runtime.db_flight_id, event_type, data)
    except Exception:
        logger.exception(
            "Failed to persist mission event %s for db_flight_id=%s",
            event_type,
            runtime.db_flight_id,
        )


async def _apply_mission_command(
    *,
    orch: Any,
    runtime: _MissionRuntimeRecord,
    command: MissionCommand,
    idempotency_key: str,
    requested_by_user_id: int,
    reason: Optional[str],
) -> MissionCommandOut:
    global _active_mission_runtime_id
    now = time.time()
    normalized_reason = (reason or "").strip() or None

    async with _mission_runtime_lock:
        existing = runtime.idempotency_results.get(idempotency_key)
        if existing is not None:
            if str(existing.get("command")) != command:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key already used for a different command.",
                )
            return MissionCommandOut.model_validate(existing)

        await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
        state_before = runtime.state
        state_after = state_before
        accepted = False
        message = ""

        target_state = _allowed_command_transition(state_before, command)
        if target_state is None:
            if _is_terminal_state(state_before):
                message = f"Mission already terminal ({state_before}); command ignored."
            else:
                message = f"Command '{command}' is invalid while mission is '{state_before}'."
        else:
            success = False
            if command == "pause":
                success = await asyncio.to_thread(orch.drone.pause_mission)
                message = (
                    "Mission paused."
                    if success
                    else "Pause command could not be applied on current drone connection."
                )
            elif command == "resume":
                success = await asyncio.to_thread(orch.drone.resume_mission)
                message = (
                    "Mission resumed."
                    if success
                    else "Resume command could not be applied on current drone connection."
                )
            elif command == "abort":
                success = await asyncio.to_thread(orch.drone.abort_mission)
                # Abort is stateful even if transport call fails; mission task checks abort flag.
                # The adapter sets the abort flag before mode-switch attempts.
                if not success:
                    logger.warning(
                        "Abort mode switch failed for mission %s; marking mission aborted anyway",
                        runtime.client_flight_id,
                    )
                message = "Mission aborted by operator."
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported command '{command}'")

            if success or command == "abort":
                accepted = True
                state_after = target_state
                runtime.state = target_state
                runtime.updated_at = now
                if (
                    _active_mission_runtime_id == runtime.client_flight_id
                    and _is_terminal_state(state_after)
                ):
                    _active_mission_runtime_id = None

        command_id = f"cmd_{int(now)}_{uuid.uuid4().hex[:10]}"
        response_payload = {
            "flight_id": runtime.client_flight_id,
            "command_id": command_id,
            "command": command,
            "idempotency_key": idempotency_key,
            "state_before": state_before,
            "state_after": state_after,
            "accepted": accepted,
            "message": message,
            "requested_at": now,
        }

        audit = _MissionCommandAudit(
            command_id=command_id,
            command=command,
            idempotency_key=idempotency_key,
            requested_by_user_id=int(requested_by_user_id),
            requested_at=now,
            state_before=state_before,
            state_after=state_after,
            accepted=accepted,
            message=message,
            reason=normalized_reason,
        )
        _record_command_audit(runtime, audit, response_payload)

    if accepted:
        await _persist_state_change_event(
            orch,
            runtime,
            event_type="mission_command",
            data={
                "command_id": command_id,
                "command": command,
                "idempotency_key": idempotency_key,
                "state_before": state_before,
                "state_after": state_after,
                "reason": normalized_reason,
                "requested_by_user_id": int(requested_by_user_id),
            },
        )
        await _persist_state_change_event(
            orch,
            runtime,
            event_type="mission_state_changed",
            data={
                "state": state_after,
                "trigger": f"command:{command}",
                "command_id": command_id,
            },
        )
        if runtime.db_flight_id is not None:
            if state_after in {"running", "paused"}:
                try:
                    db_status = _db_status_for_runtime_state(state_after)
                    await orch.repo.set_flight_status_if_active(
                        runtime.db_flight_id,
                        status=db_status,
                        note=message,
                    )
                except Exception:
                    logger.exception(
                        "Failed updating flight status to %s for db_flight_id=%s",
                        db_status.value,
                        runtime.db_flight_id,
                    )
            elif state_after == "aborted":
                try:
                    await orch.repo.finish_flight_if_in_progress(
                        runtime.db_flight_id,
                        status=FlightStatus.INTERRUPTED,
                        note=message,
                    )
                except Exception:
                    logger.exception(
                        "Failed updating flight status to interrupted for db_flight_id=%s",
                        runtime.db_flight_id,
                    )

    return MissionCommandOut.model_validate(response_payload)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/preflight/run", response_model=PreflightRunOut)
async def run_preflight(
        payload: MissionCreateIn,
        user=Depends(require_user),
):
    """Run preflight checks as a first-class API call and store a short-lived run token."""
    try:
        mission, _ = _build_mission(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    orch = await get_orchestrator()
    active_task = getattr(orch, "_active_mission_task", None)
    if active_task is not None and not active_task.done():
        raise HTTPException(
            status_code=409,
            detail="Cannot run manual preflight while a mission is currently active.",
        )

    try:
        await _ensure_drone_ready_for_preflight(orch)
        report = await orch._run_preflight_checks(
            mission.get_waypoints(),
            payload.cruise_alt,
            raise_on_fail=False,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Manual preflight run failed")
        raise HTTPException(
            status_code=500,
            detail=f"Preflight execution failed: {exc}",
        ) from exc

    rec = _store_preflight_run(
        user_id=int(user.id),
        mission_fingerprint=_mission_fingerprint(payload),
        report=report,
    )
    return _preflight_record_out(rec)


@router.get("/preflight/runs/{preflight_run_id}", response_model=PreflightRunOut)
async def get_preflight_run(
        preflight_run_id: str,
        user=Depends(require_user),
):
    rec = _get_preflight_run(preflight_run_id)
    if rec is None or rec.user_id != int(user.id):
        raise HTTPException(status_code=404, detail="Preflight run not found")
    return _preflight_record_out(rec)


@router.post("/missions", response_model=MissionCreateOut)
async def create_mission(
        payload: MissionCreateIn,
        user=Depends(require_user),
):
    """Create and start a mission — returns flight_id for WebSocket tracking.

    Supported mission types
    -----------------------
    ``"waypoints"``  – fly an ordered list of lat/lon/alt coordinates.
    ``"grid"``       – auto-generate a lawnmower survey over a field polygon.
    ``"photogrammetry"`` – run survey with camera trigger + image staging flow.
    ``"perimeter_patrol"`` / ``"private_patrol"`` – persistent property-border patrol.
    """
    global _active_mission_runtime_id
    preflight_run_id = (payload.preflight_run_id or "").strip()
    if preflight_run_id:
        rec = _get_preflight_run(preflight_run_id)
        if rec is None or rec.user_id != int(user.id):
            raise HTTPException(
                status_code=404,
                detail="Preflight run not found for this user.",
            )

        expected_fingerprint = _mission_fingerprint(payload)
        if rec.mission_fingerprint != expected_fingerprint:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Preflight run does not match this mission payload. "
                    "Run preflight again before mission start."
                ),
            )

        if not _preflight_allows_start(rec.overall_status):
            raise HTTPException(
                status_code=412,
                detail=(
                    f"Preflight status '{rec.overall_status}' does not satisfy mission start policy."
                ),
            )
    elif REQUIRE_PREFLIGHT_RUN_BEFORE_MISSION:
        raise HTTPException(
            status_code=412,
            detail=(
                "Preflight run is required before mission start. "
                "Call POST /tasks/preflight/run and provide preflight_run_id."
            ),
        )

    try:
        mission, wps_count = _build_mission(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client_flight_id = f"flight_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    orch = await get_orchestrator()
    active_task = getattr(orch, "_active_mission_task", None)
    async with _mission_runtime_lock:
        active_runtime = (
            _mission_runtimes.get(_active_mission_runtime_id)
            if _active_mission_runtime_id
            else None
        )
        if active_runtime is not None and not _is_terminal_state(active_runtime.state):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Another mission is already active "
                    f"({active_runtime.client_flight_id}, state={active_runtime.state}). "
                    "Wait for it to complete before starting a new one."
                ),
            )
        if active_task is not None and not active_task.done():
            raise HTTPException(
                status_code=409,
                detail="Another mission is already running. Wait for it to complete before starting a new one.",
            )

    orch.current_mission_name = payload.name
    orch.current_client_flight_id = client_flight_id

    now = time.time()
    patrol_task_type = None
    patrol_ai_tasks: list[str] = []
    patrol_trigger_type = None
    patrol_target_label = None
    if payload.private_patrol is not None:
        patrol_task_type = str(payload.private_patrol.task_type)
        patrol_ai_tasks = [str(x) for x in normalize_ai_tasks(payload.private_patrol.ai_tasks)]
        patrol_trigger_type = str(payload.private_patrol.trigger_type)
        patrol_target_label = payload.private_patrol.target_label

    runtime = MissionRuntimeRecord(
        client_flight_id=client_flight_id,
        user_id=int(user.id),
        mission_name=payload.name,
        mission_type=payload.mission_type.value,
        preflight_run_id=preflight_run_id or None,
        state="queued",
        created_at=now,
        updated_at=now,
        private_patrol_task_type=(
            getattr(payload.private_patrol, "task_type", None)
            if payload.private_patrol is not None
            else None
        ),
        ai_tasks=tuple(
            getattr(payload.private_patrol, "ai_tasks", ()) or ()
        ),
    )
    await mission_runtime_store.put(runtime, make_active=True)
    async with _mission_runtime_lock:
        _mission_runtimes[client_flight_id] = runtime
        _active_mission_runtime_id = client_flight_id
        _cleanup_stale_mission_runtimes(now)

    task = asyncio.create_task(
        execute_mission(
            orch,
            mission,
            payload.cruise_alt,
            payload.name,
            runtime_id=client_flight_id,
        )
    )
    orch._active_mission_task = task

    def _clear_active_mission_task(done_task: asyncio.Task) -> None:
        if getattr(orch, "_active_mission_task", None) is done_task:
            orch._active_mission_task = None

    task.add_done_callback(_clear_active_mission_task)

    return MissionCreateOut(
        flight_id=client_flight_id,
        status="queued",
        mission_name=payload.name,
        mission_type=payload.mission_type.value,
        waypoints_count=wps_count,
        preflight_run_id=preflight_run_id or None,
    )


@router.get("/missions/{flight_id}", response_model=MissionRuntimeOut)
async def get_mission_runtime(
    flight_id: str,
    user=Depends(require_user),
):
    runtime = await _get_runtime_for_user(flight_id, user_id=int(user.id))
    orch = await get_orchestrator()
    async with _mission_runtime_lock:
        await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
        return _runtime_to_out(runtime)


@router.get("/missions/{flight_id}/commands", response_model=List[MissionCommandAuditOut])
async def get_mission_command_audit(
    flight_id: str,
    user=Depends(require_user),
):
    runtime = await _get_runtime_for_user(flight_id, user_id=int(user.id))
    async with _mission_runtime_lock:
        return [_audit_to_out(item) for item in runtime.command_audit]


@router.post(
    "/missions/{flight_id}/commands/{command}",
    response_model=MissionCommandOut,
)
async def issue_mission_command(
    flight_id: str,
    command: MissionCommand,
    payload: MissionCommandIn,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    user=Depends(require_user),
):
    runtime = await _get_runtime_for_user(flight_id, user_id=int(user.id))
    orch = await get_orchestrator()
    idempotency_key = _resolve_idempotency_key(
        payload.idempotency_key,
        idempotency_key_header,
    )

    result = await _apply_mission_command(
        orch=orch,
        runtime=runtime,
        command=command,
        idempotency_key=idempotency_key,
        requested_by_user_id=int(user.id),
        reason=payload.reason,
    )

    if result.accepted and command == "abort" and result.state_before == "queued":
        active_task = getattr(orch, "_active_mission_task", None)
        if active_task is not None and not active_task.done():
            active_task.cancel()
            logger.info("Cancelled queued mission task for %s after abort command", flight_id)

    return result


@router.get("/flight/status")
async def get_flight_status():
    """Current flight status + telemetry summary."""
    try:
        orch = await get_orchestrator()
        runtime_out: Optional[MissionRuntimeOut] = None
        async with _mission_runtime_lock:
            runtime = (
                _mission_runtimes.get(_active_mission_runtime_id)
                if _active_mission_runtime_id
                else None
            )
            if runtime is not None:
                await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
                runtime_out = _runtime_to_out(runtime)

        flight_id = runtime_out.flight_id if runtime_out is not None else None
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
            "mission_lifecycle": runtime_out.model_dump() if runtime_out is not None else None,
            "command_capabilities": {
                "pause": runtime_out is not None and runtime_out.state == "running",
                "resume": runtime_out is not None and runtime_out.state == "paused",
                "abort": runtime_out is not None and runtime_out.state in {"queued", "running", "paused"},
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


class PrivatePatrolTaskTemplateOut(BaseModel):
    id: str
    label: str
    purpose: str
    description: str
    default_params: dict
    ai_tasks: List[str]


class PrivatePatrolTaskCatalogOut(BaseModel):
    mission_category: str
    tasks: List[PrivatePatrolTaskTemplateOut]


class PrivatePatrolPreviewIn(BaseModel):
    task_type: Literal[
        "perimeter_patrol",
        "waypoint_patrol",
        "grid_surveillance",
        "event_triggered_patrol",
    ] = "perimeter_patrol"
    property_polygon_lonlat: Optional[List[List[float]]] = Field(default=None, min_length=3)
    key_points_lonlat: Optional[List[List[float]]] = Field(default=None, min_length=2)
    cruise_alt: float = Field(default=30.0, gt=0, le=500.0)
    path_offset_m: float = Field(default=15.0, ge=0.0, le=120.0)
    direction: Literal["clockwise", "counterclockwise"] = "clockwise"
    patrol_loops: int = Field(default=1, ge=1, le=200)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    camera_angle_deg: float = Field(default=35.0, ge=0.0, le=90.0)
    camera_overlap_pct: float = Field(default=50.0, ge=0.0, le=95.0)
    max_segment_length_m: float = Field(default=20.0, gt=1.0, le=300.0)
    hover_time_s: float = Field(default=15.0, ge=1.0, le=300.0)
    camera_scan_yaw_deg: float = Field(default=360.0, ge=0.0, le=360.0)
    zoom_capture: bool = True
    return_to_start: bool = True
    grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    grid_angle_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    safety_inset_m: float = Field(default=2.0, ge=0.0, le=100.0)
    trigger_type: PatrolTriggerType = "fence_alarm"
    trigger_event_location_lonlat: Optional[List[float]] = Field(default=None, min_length=2, max_length=2)
    target_label: Optional[str] = Field(default=None, max_length=120)
    verification_loiter_s: float = Field(default=45.0, ge=0.0, le=600.0)
    verification_radius_m: float = Field(default=18.0, ge=0.0, le=150.0)
    track_target: bool = True
    auto_stream_video: bool = True
    ai_tasks: List[PatrolTaskType] = Field(default_factory=lambda: list(PATROL_AI_TASKS))

    @model_validator(mode="after")
    def _validate_by_task(self) -> "PrivatePatrolPreviewIn":
        if self.task_type in {"perimeter_patrol", "grid_surveillance"}:
            if not self.property_polygon_lonlat or len(self.property_polygon_lonlat) < 3:
                raise ValueError(
                    f"task_type='{self.task_type}' requires property_polygon_lonlat with at least 3 coordinate pairs."
                )
        elif self.task_type == "waypoint_patrol":
            if not self.key_points_lonlat or len(self.key_points_lonlat) < 2:
                raise ValueError(
                    "task_type='waypoint_patrol' requires key_points_lonlat with at least 2 coordinate pairs."
                )
        elif self.task_type == "event_triggered_patrol":
            _ = normalize_trigger_type(self.trigger_type)
            has_event_loc = bool(self.trigger_event_location_lonlat and len(self.trigger_event_location_lonlat) == 2)
            if self.trigger_type == "night_schedule":
                if not has_event_loc and not (self.property_polygon_lonlat and len(self.property_polygon_lonlat) >= 3):
                    raise ValueError(
                        "task_type='event_triggered_patrol' with trigger_type='night_schedule' "
                        "requires trigger_event_location_lonlat or property_polygon_lonlat."
                    )
            elif not has_event_loc:
                raise ValueError(
                    "task_type='event_triggered_patrol' requires trigger_event_location_lonlat=[lon, lat]."
                )
        return self


class PrivatePatrolPreviewOut(BaseModel):
    waypoints: List[dict]
    work_leg_mask: List[bool]
    stats: dict
    camera: dict
    ai_tasks: List[str]


@router.get(
    "/missions/private-patrol/tasks",
    response_model=PrivatePatrolTaskCatalogOut,
)
async def get_private_patrol_tasks() -> PrivatePatrolTaskCatalogOut:
    return PrivatePatrolTaskCatalogOut(
        mission_category="private_patrol",
        tasks=[
            PrivatePatrolTaskTemplateOut.model_validate(item)
            for item in private_patrol_task_catalog()
        ],
    )


@router.post("/missions/private-patrol/preview", response_model=PrivatePatrolPreviewOut)
async def preview_private_patrol(payload: PrivatePatrolPreviewIn) -> PrivatePatrolPreviewOut:
    try:
        ai_tasks = normalize_ai_tasks(payload.ai_tasks)
        if payload.task_type == "event_triggered_patrol":
            event_lon, event_lat = _resolve_trigger_event_location(
                trigger_type=payload.trigger_type,
                trigger_event_location_lonlat=payload.trigger_event_location_lonlat,
                property_polygon_lonlat=payload.property_polygon_lonlat,
            )
            plan = generate_event_triggered_patrol_plan(
                (event_lon, event_lat),
                altitude_agl_m=float(payload.cruise_alt),
                verification_radius_m=float(payload.verification_radius_m),
            )
            waypoints = plan.waypoints
        elif payload.task_type == "grid_surveillance":
            polygon = [tuple(pt) for pt in (payload.property_polygon_lonlat or [])]
            plan = generate_grid_surveillance_plan(
                polygon,
                altitude_agl_m=float(payload.cruise_alt),
                grid_spacing_m=float(payload.grid_spacing_m),
                grid_angle_deg=float(payload.grid_angle_deg),
                safety_inset_m=float(payload.safety_inset_m),
            )
            waypoints = plan.waypoints
        elif payload.task_type == "waypoint_patrol":
            key_points = [tuple(pt) for pt in (payload.key_points_lonlat or [])]
            plan = generate_waypoint_patrol_plan(
                key_points,
                altitude_agl_m=float(payload.cruise_alt),
                return_to_start=bool(payload.return_to_start),
            )
            waypoints = plan.waypoints
        else:
            direction = normalize_patrol_direction(payload.direction)
            polygon = [tuple(pt) for pt in (payload.property_polygon_lonlat or [])]
            plan = generate_private_patrol_plan(
                polygon,
                altitude_agl_m=float(payload.cruise_alt),
                path_offset_m=float(payload.path_offset_m),
                direction=direction,
                max_segment_length_m=float(payload.max_segment_length_m),
            )
            waypoints = repeat_patrol_loops(plan.waypoints, loops=int(payload.patrol_loops))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_route_m = 0.0
    if len(waypoints) >= 2:
        for a, b in zip(waypoints, waypoints[1:]):
            total_route_m += math.hypot(
                (float(b.lat) - float(a.lat)) * 111_132.0,
                (float(b.lon) - float(a.lon))
                * 111_320.0
                * math.cos(math.radians((float(a.lat) + float(b.lat)) / 2.0)),
            )
    mask_len = max(0, len(waypoints) - 1)

    if payload.task_type == "waypoint_patrol":
        key_points_count = len(payload.key_points_lonlat or [])
        hover_total_s = float(payload.hover_time_s) * float(key_points_count)
        est_duration_s = (total_route_m / max(0.1, float(payload.speed_mps))) + hover_total_s
        stats = {
            **plan.stats,
            "task_type": payload.task_type,
            "key_points": key_points_count,
            "waypoints": len(waypoints),
            "hover_time_s": float(payload.hover_time_s),
            "hover_total_s": round(hover_total_s, 1),
            "total_route_m": round(total_route_m, 1),
            "estimated_duration_s": round(est_duration_s, 1),
            "speed_mps": float(payload.speed_mps),
        }
        return PrivatePatrolPreviewOut(
            waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
            work_leg_mask=[True] * mask_len,
            stats=stats,
            camera={
                "scan_yaw_deg": float(payload.camera_scan_yaw_deg),
                "zoom_capture": bool(payload.zoom_capture),
            },
            ai_tasks=[str(task) for task in ai_tasks],
        )

    if payload.task_type == "event_triggered_patrol":
        travel_s = total_route_m / max(0.1, float(payload.speed_mps))
        est_duration_s = travel_s + float(payload.verification_loiter_s)
        action = trigger_action_profile(payload.trigger_type, target_label=payload.target_label)
        stats = {
            **plan.stats,
            "task_type": payload.task_type,
            "trigger_type": str(payload.trigger_type),
            "trigger_action": action.get("action"),
            "waypoints": len(waypoints),
            "total_route_m": round(total_route_m, 1),
            "estimated_duration_s": round(est_duration_s, 1),
            "verification_loiter_s": float(payload.verification_loiter_s),
            "speed_mps": float(payload.speed_mps),
        }
        return PrivatePatrolPreviewOut(
            waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
            work_leg_mask=[True] * mask_len,
            stats=stats,
            camera={
                "stream_to_operator": bool(payload.auto_stream_video),
                "track_target": bool(payload.track_target),
                "target_label": payload.target_label,
            },
            ai_tasks=[str(task) for task in ai_tasks],
        )

    if payload.task_type == "grid_surveillance":
        est_duration_s = total_route_m / max(0.1, float(payload.speed_mps))
        stats = {
            **plan.stats,
            "task_type": payload.task_type,
            "waypoints": len(waypoints),
            "total_route_m": round(total_route_m, 1),
            "estimated_duration_s": round(est_duration_s, 1),
            "speed_mps": float(payload.speed_mps),
        }
        return PrivatePatrolPreviewOut(
            waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
            work_leg_mask=[True] * mask_len,
            stats=stats,
            camera={
                "mode": "wide_coverage",
                "grid_spacing_m": float(payload.grid_spacing_m),
            },
            ai_tasks=[str(task) for task in ai_tasks],
        )

    est_duration_s = total_route_m / max(0.1, float(payload.speed_mps))
    trigger_distance_m = estimate_camera_trigger_distance_m(
        altitude_agl_m=float(payload.cruise_alt),
        overlap_pct=float(payload.camera_overlap_pct),
    )
    stats = {
        **plan.stats,
        "task_type": payload.task_type,
        "patrol_loops": int(payload.patrol_loops),
        "waypoints": len(waypoints),
        "total_route_m": round(total_route_m, 1),
        "estimated_duration_s": round(est_duration_s, 1),
        "speed_mps": float(payload.speed_mps),
    }
    return PrivatePatrolPreviewOut(
        waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
        work_leg_mask=[True] * mask_len,
        stats=stats,
        camera={
            "angle_deg": float(payload.camera_angle_deg),
            "overlap_pct": float(payload.camera_overlap_pct),
            "trigger_distance_m": round(trigger_distance_m, 2),
        },
        ai_tasks=[str(task) for task in ai_tasks],
    )
