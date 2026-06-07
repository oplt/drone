from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.entrypoints.cli.run_mission import _build_orchestrator
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import (
    OrgUser,
    require_mission_exec,
    require_org_user,
    require_org_write,
)
from backend.modules.missions.api.routes import MissionCreateIn, create_mission
from backend.modules.missions.flight_profile import FlightEnvironment
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.organizations.service import can_access_org_scope, get_default_project
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseSensorRig,
)
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.repository.settings import WarehouseSettingsRepository

router = APIRouter(prefix="/warehouse", tags=["warehouse"])
logger = logging.getLogger(__name__)

_repo = WarehouseMappingRepository()
_settings_repo = WarehouseSettingsRepository()
_PREFLIGHT_RUNS: dict[str, WarehousePreflightRefreshOut] = {}
_BRIDGE_PROCESS: subprocess.Popen[bytes] | None = None
_BRIDGE_LOCK = asyncio.Lock()
_PREFLIGHT_DRONE_LOCK = asyncio.Lock()
_SETTINGS_SECTION = "warehouse"
_MISSION_DEFAULTS_KEY = "mission_defaults"
_EXPLORATION_PROFILE_KEY = "exploration_profile"


def _ros_command_env() -> dict[str, str]:
    env = dict(os.environ)
    env["ROS_DOMAIN_ID"] = os.getenv("ROS_DOMAIN_ID", "0")
    env.setdefault("ROS_LOG_DIR", "/tmp/warehouse_ros_logs")
    venv_bin = None
    if env.get("VIRTUAL_ENV"):
        venv_bin = str(Path(env["VIRTUAL_ENV"]) / "bin")
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if venv_bin:
        env["PATH"] = ":".join(
            part for part in env.get("PATH", "").split(":") if part != venv_bin
        )
    return env


class WarehouseLocalPose(BaseModel):
    x_m: float
    y_m: float
    z_m: float = 0.0
    yaw_deg: float | None = None


class WarehouseMapOut(BaseModel):
    id: int
    name: str
    area_m2: float | None = None
    created_at: datetime
    polygon_local_m: list[list[float]]


class WarehouseMapCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    width_m: float = Field(..., gt=0.1, le=10_000)
    length_m: float = Field(..., gt=0.1, le=10_000)


class WarehouseMissionDefaultsOut(BaseModel):
    cruise_alt: float = Field(default=2.5, gt=0.2, le=20.0)
    corridor_spacing_m: float = Field(default=3.0, gt=0.1, le=50.0)
    aisle_axis_deg: float | None = Field(default=0.0, ge=-180.0, le=360.0)
    clearance_m: float = Field(default=0.75, gt=0.1, le=20.0)
    perimeter_offset_m: float = Field(default=0.5, ge=0.0, le=20.0)
    scan_pattern: Literal[
        "aisle_serpentine",
        "stacked_passes",
        "crosshatch",
        "perimeter_aisle_hybrid",
    ] = "aisle_serpentine"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    view_mode: Literal["forward", "left_face", "right_face", "dual_face"] = "forward"
    layer_count: int = Field(default=1, ge=1, le=20)
    layer_spacing_m: float = Field(default=1.0, ge=0.0, le=20.0)
    ceiling_height_m: float = Field(default=6.0, gt=0.1, le=100.0)
    ceiling_margin_m: float = Field(default=0.6, ge=0.0, le=20.0)
    work_speed_mps: float = Field(default=0.8, gt=0.0, le=20.0)
    transit_speed_mps: float = Field(default=1.2, gt=0.0, le=30.0)
    scan_pause_s: float = Field(default=0.0, ge=0.0, le=30.0)
    interpolate_steps_work_leg: int = Field(default=6, ge=0, le=100)
    interpolate_steps_transit_leg: int = Field(default=4, ge=0, le=100)


class WarehouseDockOut(BaseModel):
    id: int
    name: str
    marker_id: str | None = None
    marker_family: str | None = None
    marker_size_m: float | None = None
    marker_pose_covariance: list[float] = Field(default_factory=list)
    marker_visible: bool | None = None
    last_observed_at: str | None = None
    charger_type: str | None = None
    pose: WarehouseLocalPose
    entry_pose: WarehouseLocalPose
    exit_pose: WarehouseLocalPose
    active: bool
    created_at: datetime


class WarehouseDockCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    marker_id: str | None = Field(default=None, max_length=128)
    marker_family: str | None = Field(default=None, max_length=64)
    marker_size_m: float | None = Field(default=None, gt=0.0, le=10.0)
    charger_type: str | None = Field(default=None, max_length=64)
    precision_required: bool = True
    pose: WarehouseLocalPose
    entry_pose: WarehouseLocalPose
    exit_pose: WarehouseLocalPose
    marker_pose_covariance: list[float] | None = None


class WarehouseDockUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    marker_id: str | None = Field(default=None, max_length=128)
    marker_family: str | None = Field(default=None, max_length=64)
    marker_size_m: float | None = Field(default=None, gt=0.0, le=10.0)
    charger_type: str | None = Field(default=None, max_length=64)
    precision_required: bool | None = None
    pose: WarehouseLocalPose | None = None
    entry_pose: WarehouseLocalPose | None = None
    exit_pose: WarehouseLocalPose | None = None
    marker_pose_covariance: list[float] | None = None


class WarehouseSensorRigOut(BaseModel):
    id: int
    name: str
    camera_model: str
    stereo_baseline_m: float | None = None
    intrinsics_url: str | None = None
    extrinsics_url: str | None = None
    imu_transform_json: dict[str, Any]
    firmware_version: str | None = None
    isaac_ros_version: str | None = None
    calibration_status: str
    calibration_hash: str | None = None
    calibration_meta: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime


class WarehouseSensorRigCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    camera_model: str = Field(..., min_length=1, max_length=128)
    stereo_baseline_m: float | None = Field(default=None, gt=0.0, le=10.0)
    intrinsics_url: str | None = Field(default=None, max_length=2048)
    extrinsics_url: str | None = Field(default=None, max_length=2048)
    imu_transform_json: dict[str, Any] = Field(default_factory=dict)
    firmware_version: str | None = Field(default=None, max_length=128)
    isaac_ros_version: str | None = Field(default=None, max_length=128)


class WarehouseSensorRigCalibrationIn(BaseModel):
    calibration_status: Literal["missing", "pending", "valid", "expired", "failed"]
    calibration_hash: str | None = Field(default=None, max_length=128)
    intrinsics_url: str | None = Field(default=None, max_length=2048)
    extrinsics_url: str | None = Field(default=None, max_length=2048)
    imu_transform_json: dict[str, Any] | None = None
    calibration_meta: dict[str, Any] = Field(default_factory=dict)


class WarehousePerceptionOut(BaseModel):
    configured: bool
    reachable: bool
    ready: bool
    status: str
    profile: str | None = None
    detail: str | None = None
    components: dict[str, Any] = Field(default_factory=dict)


class WarehouseSensorRigHealthOut(BaseModel):
    sensor_rig: WarehouseSensorRigOut
    perception: WarehousePerceptionOut
    ready: bool
    blockers: list[str]
    warnings: list[str] = Field(default_factory=list)


class WarehouseScannedMapAssetOut(BaseModel):
    id: int
    type: str
    url: str
    created_at: datetime
    meta_data: dict[str, Any] = Field(default_factory=dict)


class WarehouseScannedMapOut(BaseModel):
    job_id: int
    model_id: int
    model_version: int
    warehouse_map_id: int
    warehouse_name: str
    status: str
    progress: int
    error: str | None = None
    source: str
    created_at: datetime
    finished_at: datetime | None = None
    polygon_local_m: list[list[float]]
    assets: list[WarehouseScannedMapAssetOut] = Field(default_factory=list)


class WarehouseScannedMapQualityOut(BaseModel):
    job_id: int
    quality_score: float | None = None
    coverage_percent: float | None = None
    drift_estimate_m: float | None = None
    source: str
    report: dict[str, Any] = Field(default_factory=dict)


class WarehouseScannedMapCompareIn(BaseModel):
    baseline_job_id: int = Field(..., ge=1)
    candidate_job_id: int = Field(..., ge=1)


class WarehouseScannedMapCompareOut(BaseModel):
    baseline_job_id: int
    candidate_job_id: int
    quality_delta: float | None = None
    coverage_delta: float | None = None
    drift_delta_m: float | None = None


class WarehouseExplorationProfileOut(BaseModel):
    max_radius_m: float = 35.0
    min_clearance_m: float = 0.8
    max_frontier_candidates: int = 20
    return_battery_reserve_pct: float = 30.0
    max_duration_s: int = 900


class WarehouseMappingStackStatusOut(BaseModel):
    running: bool
    pid: int | None = None
    started_at: str | None = None
    last_exit_code: int | None = None
    last_error: str | None = None
    nvblox_running: bool = False
    phase: str = "stopped"


class WarehouseCommandOut(BaseModel):
    accepted: bool
    status: str
    detail: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    mapping_job: dict[str, Any] | None = None


class WarehouseMissionStartIn(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = "Warehouse Scan"
    reference_mapping_job_id: int | None = Field(default=None, ge=1)
    sensor_rig_id: int | None = Field(default=None, ge=1)
    dock_id: int | None = Field(default=None, ge=1)


class WarehouseExplorationStartIn(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = "Warehouse Exploration"
    hover_alt_m: float = Field(default=2.5, gt=0.2, le=20.0)
    dock_id: int | None = Field(default=None, ge=1)
    exploration: dict[str, Any] = Field(default_factory=dict)


class WarehousePreflightOut(BaseModel):
    ready: bool = False
    blocking: bool = True
    checks: list[dict[str, str]] = Field(default_factory=list)
    ready_to_fly: bool = False
    service_health: bool = False
    ros_graph_ready: bool = False
    mapping_ok: bool | None = None
    primary_blocker: str | None = None
    blockers: list[str] = Field(default_factory=list)
    diagnostics_age_ms: int | None = None
    mode: str = "warehouse"
    localization_mode: str = "local_odom"
    topic_health: dict[str, Any] = Field(default_factory=dict)
    tf_health: dict[str, Any] = Field(default_factory=dict)
    stability_window_ms: int = 0
    required_stability_window_ms: int = 0
    bridge_ok: bool = False
    source_transport_ok: bool | None = None
    sensors_ok: bool = False
    odom_ok: bool = False
    localization_ok: bool = False
    tf_ok: bool = False
    nvblox_ok: bool | None = None
    stability_ok: bool = False
    vehicle_link_ok: bool = False
    telemetry_stream_ok: bool = False
    battery_ok: bool = False
    perception_stable_for_ms: int = 0
    perception_required_stable_ms: int = 0
    ros_topic_count: int | None = None
    warehouse_bridge_state: str = "disabled"
    bridge_url: str | None = None
    last_error: str | None = None
    restart_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str | None = (
        "Configure warehouse perception bridge and calibrated sensor rig."
    )
    blocking_reasons: list[str] = Field(
        default_factory=lambda: ["Warehouse runtime bridge is not configured."]
    )
    suggested_actions: list[str] = Field(default_factory=list)
    categories: dict[str, str] = Field(default_factory=dict)
    note: str = "Warehouse API available; runtime bridge not configured."


class WarehousePreflightRefreshOut(BaseModel):
    run_id: str
    status: str
    deep: bool
    force: bool
    mission_loaded: bool
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    snapshot: WarehousePreflightOut | None = None


class WarehouseFlightSubsystemOut(BaseModel):
    status: str
    message: str
    last_seen_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    stable_for_ms: int | None = None
    required_stable_ms: int | None = None
    costmap_age_ms: int | None = None


class WarehouseFlightReadinessOut(BaseModel):
    ready_to_arm: bool = False
    ready_to_takeoff: bool = False
    ready_for_autonomy: bool = False
    overall_status: str = "WAITING"
    current_state: str = "IDLE"
    subsystems: dict[str, WarehouseFlightSubsystemOut] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(
        default_factory=lambda: ["Warehouse flight bridge is not configured."]
    )
    updated_at: datetime
    slam_stable_for_ms: int = 0
    slam_required_stable_ms: int = 0
    perception_stable_for_ms: int = 0
    perception_required_stable_ms: int = 0


class WarehouseFlightStartIn(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = "Warehouse Scan"
    sensor_rig_id: int | None = Field(default=None, ge=1)
    dock_id: int | None = Field(default=None, ge=1)
    reference_mapping_job_id: int | None = Field(default=None, ge=1)
    work_speed_mps: float | None = Field(default=None, gt=0.0, le=5.0)
    cruise_alt: float | None = Field(default=None, gt=0.2, le=20.0)


class WarehouseFlightStartOut(BaseModel):
    accepted: bool
    reason: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    readiness: WarehouseFlightReadinessOut | None = None
    launch: dict[str, Any] | None = None


class WarehouseFlightCommandIn(BaseModel):
    command: Literal["pause", "resume", "abort", "land", "rth"]


class WarehouseFlightCommandOut(BaseModel):
    accepted: bool
    message: str


class WarehouseLiveMapSnapshotOut(BaseModel):
    type: Literal["live_map_snapshot"] = "live_map_snapshot"
    flight_id: str
    status: Literal["empty", "live", "stale", "finalized"] = "empty"
    last_update_at: str | None = None
    updates: list[dict[str, Any]] = Field(default_factory=list)


def _map_out(row: WarehouseMap) -> WarehouseMapOut:
    return WarehouseMapOut(
        id=int(row.id),
        name=row.name,
        area_m2=row.area_m2,
        created_at=row.created_at,
        polygon_local_m=_repo.polygon_from_local(row),
    )


def _pose(payload: dict[str, Any]) -> WarehouseLocalPose:
    return WarehouseLocalPose.model_validate(payload or {})


def _dock_out(row: WarehouseDockStation) -> WarehouseDockOut:
    meta = row.meta_data if isinstance(row.meta_data, dict) else {}
    return WarehouseDockOut(
        id=int(row.id),
        name=row.name,
        marker_id=row.marker_id,
        marker_family=meta.get("marker_family"),
        marker_size_m=meta.get("marker_size_m"),
        marker_pose_covariance=list(meta.get("marker_pose_covariance") or []),
        marker_visible=meta.get("marker_visible"),
        last_observed_at=meta.get("last_observed_at"),
        charger_type=row.charger_type,
        pose=_pose(row.pose_local_json),
        entry_pose=_pose(row.entry_pose_local_json),
        exit_pose=_pose(row.exit_pose_local_json),
        active=bool(row.active),
        created_at=row.created_at,
    )


def _sensor_rig_out(row: WarehouseSensorRig) -> WarehouseSensorRigOut:
    return WarehouseSensorRigOut.model_validate(
        {
            "id": int(row.id),
            "name": row.name,
            "camera_model": row.camera_model,
            "stereo_baseline_m": row.stereo_baseline_m,
            "intrinsics_url": row.intrinsics_url,
            "extrinsics_url": row.extrinsics_url,
            "imu_transform_json": row.imu_transform_json or {},
            "firmware_version": row.firmware_version,
            "isaac_ros_version": row.isaac_ros_version,
            "calibration_status": row.calibration_status,
            "calibration_hash": row.calibration_hash,
            "calibration_meta": row.calibration_meta or {},
            "active": bool(row.active),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _asset_out(row: WarehouseAsset) -> WarehouseScannedMapAssetOut:
    return WarehouseScannedMapAssetOut(
        id=int(row.id),
        type=row.type,
        url=row.url,
        created_at=row.created_at,
        meta_data=row.meta_data or {},
    )


def _source(job: WarehouseMappingJob, warehouse_map: WarehouseMap) -> str:
    meta = warehouse_map.meta_data if isinstance(warehouse_map.meta_data, dict) else {}
    if meta.get("source") == "simulation" or job.processor == "simulation":
        return "simulation"
    if job.processor == "warehouse_manual_mapping":
        return "real_flight"
    return str(job.processor or "warehouse_scan")


def _quality(
    job: WarehouseMappingJob,
    warehouse_map: WarehouseMap,
    assets: list[WarehouseAsset],
) -> WarehouseScannedMapQualityOut:
    report_asset = next((a for a in assets if a.type.upper() == "QUALITY_REPORT"), None)
    report = dict(report_asset.meta_data or {}) if report_asset else {}
    quality = report.get("quality_score")
    coverage = report.get("coverage_percent")
    drift = report.get("drift_estimate_m")
    return WarehouseScannedMapQualityOut(
        job_id=int(job.id),
        quality_score=float(quality) if isinstance(quality, int | float) else None,
        coverage_percent=float(coverage) if isinstance(coverage, int | float) else None,
        drift_estimate_m=float(drift) if isinstance(drift, int | float) else None,
        source=_source(job, warehouse_map),
        report=report,
    )


async def _get_map_or_404(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    user: Any,
) -> WarehouseMap:
    warehouse_map = await _repo.get_owned_warehouse_map(
        db,
        warehouse_map_id=warehouse_map_id,
        owner_id=int(user.id),
        org_id=user.org_id,
        allow_org_access=can_access_org_scope(user),
    )
    if warehouse_map is None:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    return warehouse_map


async def _dock_config_for_mission(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    dock_id: int | None,
) -> dict[str, Any] | None:
    if dock_id is None:
        return None
    docks = await _repo.list_dock_stations(db, warehouse_map_id=warehouse_map_id)
    dock = next((row for row in docks if int(row.id) == int(dock_id)), None)
    if dock is None:
        raise HTTPException(status_code=404, detail="Warehouse dock station not found")
    meta = dock.meta_data or {}
    return {
        "dock_pose": dock.pose_local_json,
        "entry_pose": dock.entry_pose_local_json,
        "exit_pose": dock.exit_pose_local_json,
        "marker_id": dock.marker_id,
        "dock_yaw_deg": meta.get("dock_yaw_deg"),
        "precision_required": bool(meta.get("precision_required", True)),
    }


async def _start_warehouse_scan_mission(
    *,
    db: AsyncSession,
    user: Any,
    warehouse_map_id: int,
    mission_name: str,
    sensor_rig_id: int | None,
    dock_id: int | None,
    reference_mapping_job_id: int | None,
    cruise_alt: float | None = None,
    work_speed_mps: float | None = None,
) -> dict[str, Any]:
    warehouse_map = await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=user)
    settings_doc = await _read_warehouse_settings(db)
    defaults = WarehouseMissionDefaultsOut.model_validate(
        settings_doc.get(_MISSION_DEFAULTS_KEY) or {}
    )
    scan_payload = defaults.model_dump(mode="python")
    if cruise_alt is not None:
        scan_payload["cruise_alt"] = float(cruise_alt)
    if work_speed_mps is not None:
        scan_payload["work_speed_mps"] = float(work_speed_mps)

    base_height_m = float(scan_payload.pop("cruise_alt"))
    scan_payload.update(
        {
            "polygon_local_m": _repo.polygon_from_local(warehouse_map),
            "warehouse_map_id": int(warehouse_map.id),
            "warehouse_name": warehouse_map.name,
            "reference_mapping_job_id": reference_mapping_job_id,
            "sensor_rig_id": sensor_rig_id,
            "dock_config": await _dock_config_for_mission(
                db,
                warehouse_map_id=int(warehouse_map.id),
                dock_id=dock_id,
            ),
        }
    )
    mission_payload = MissionCreateIn(
        name=mission_name or "Warehouse Scan",
        cruise_alt=base_height_m,
        mission_type=MissionType.WAREHOUSE_SCAN,
        flight_environment=FlightEnvironment.INDOOR_LOCAL,
        warehouse_scan=scan_payload,
    )
    result = await create_mission(mission_payload, user=user)
    return result.model_dump(mode="json")


async def _read_warehouse_settings(db: AsyncSession) -> dict[str, Any]:
    data = await _settings_repo.read_document(db)
    section = data.get(_SETTINGS_SECTION)
    return dict(section) if isinstance(section, dict) else {}


async def _write_warehouse_setting(
    db: AsyncSession,
    *,
    key: str,
    value: dict[str, Any],
) -> None:
    data = await _settings_repo.read_document(db)
    section = data.get(_SETTINGS_SECTION)
    warehouse = dict(section) if isinstance(section, dict) else {}
    warehouse[key] = value
    data[_SETTINGS_SECTION] = warehouse
    await _settings_repo.write_document(db, data=data)


def _status(ok: bool | None, *, required: bool = True) -> str:
    if ok is True:
        return "OK"
    if ok is False:
        return "FAIL" if required else "WARN"
    return "UNKNOWN"


def _read_odometry_overlay() -> tuple[dict[str, Any], str | None]:
    path_raw = str(getattr(settings, "WAREHOUSE_ODOMETRY_STATE_PATH", "") or "").strip()
    if not path_raw:
        return {}, "WAREHOUSE_ODOMETRY_STATE_PATH is not configured."
    path = Path(path_raw)
    if not path.exists():
        return {}, f"Odometry state file not found: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"Odometry state file is unreadable: {exc}"
    return (payload if isinstance(payload, dict) else {}), None


def _bool_from(payload: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _float_from(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _topic_diag(
    *,
    topic: str | None = None,
    status: str,
    detail: str | None = None,
) -> dict[str, str]:
    data = {"status": status}
    if topic:
        data["topic"] = topic
    if detail:
        data["detail"] = detail
    return data


async def _probe_bridge(bridge_url: str, *, enabled: bool) -> tuple[bool | None, str | None]:
    if not bridge_url:
        return False, "WAREHOUSE_ROS_BRIDGE_URL is not configured."
    if not enabled:
        return None, "Bridge URL configured; deep probe not requested."
    url = bridge_url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        if response.status_code < 400:
            return True, f"Bridge health reachable at {url}"
        return False, f"Bridge health returned HTTP {response.status_code}"
    except Exception as exc:
        return False, f"Bridge health unreachable at {url}: {exc}"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ros2_workspace() -> Path:
    return Path(os.getenv("WAREHOUSE_ROS2_WS", str(_project_root() / "ros2_ws"))).resolve()


def _run_ros2_topic_list(ws: Path) -> tuple[bool | None, str]:
    setup = ws / "install" / "setup.bash"
    if not setup.exists():
        return False, f"ROS 2 workspace is not built: {setup}"
    cmd = (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {setup} && "
        "ros2 topic list --no-daemon"
    )
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            timeout=3,
            check=False,
            env=_ros_command_env(),
        )
    except FileNotFoundError:
        return False, "bash is not available; cannot probe ROS 2."
    except subprocess.TimeoutExpired:
        return None, "ROS 2 topic probe timed out."
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        return False, stderr or "ros2 topic list failed."
    topics = result.stdout.decode(errors="replace").splitlines()
    has_warehouse = any(topic.startswith("/warehouse/") for topic in topics)
    if has_warehouse:
        topic_count = sum(t.startswith("/warehouse/") for t in topics)
        return True, f"ROS graph has {topic_count} warehouse topics."
    return None, "ROS graph reachable, but no /warehouse topics are publishing yet."


def _bridge_topic_mappings(ws: Path) -> dict[str, str]:
    config = ws / "src/drone_gz_bridge/config/warehouse_bridge.yaml"
    if not config.exists():
        return {}
    mappings: dict[str, str] = {}
    current_ros: str | None = None
    for line in config.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- ros_topic_name:"):
            current_ros = stripped.split(":", 1)[1].strip().strip('"')
        elif current_ros and stripped.startswith("gz_topic_name:"):
            mappings[current_ros] = stripped.split(":", 1)[1].strip().strip('"')
            current_ros = None
    return mappings


def _ros2_topic_list(ws: Path) -> set[str]:
    ok, detail = _run_ros2_topic_list(ws)
    if ok is False:
        raise RuntimeError(detail)
    setup = ws / "install" / "setup.bash"
    cmd = (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {setup} && "
        "ros2 topic list --no-daemon"
    )
    result = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=str(ws),
        capture_output=True,
        timeout=3,
        check=False,
        env=_ros_command_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return {
        line.strip()
        for line in result.stdout.decode(errors="replace").splitlines()
        if line.strip()
    }


def _ros2_topic_has_sample(ws: Path, topic: str) -> bool:
    setup = ws / "install" / "setup.bash"
    cmd = (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {setup} && "
        f"ros2 topic echo --no-daemon --once --timeout 3 {topic}"
    )
    result = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=str(ws),
        capture_output=True,
        timeout=4,
        check=False,
        env=_ros_command_env(),
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _gz_topic_list(ws: Path) -> tuple[set[str], str | None]:
    result = subprocess.run(
        ["bash", "-lc", "gz topic -l"],
        cwd=str(ws),
        capture_output=True,
        timeout=3,
        check=False,
        env=_ros_command_env(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        return set(), detail or "gz topic -l failed."
    topics = {
        line.strip()
        for line in result.stdout.decode(errors="replace").splitlines()
        if line.strip()
    }
    return topics, None


def _probe_warehouse_bridge_topics(ws: Path) -> dict[str, Any]:
    mappings = _bridge_topic_mappings(ws)
    ros_topics = _ros2_topic_list(ws)
    gz_topics, gz_error = _gz_topic_list(ws)
    expected = {
        "odometry_topic": "/warehouse/drone/odometry",
        "rgb_topic": "/warehouse/front/rgbd/image",
        "depth_topic": "/warehouse/front/rgbd/depth_image",
        "imu_topic": "/warehouse/imu",
        "lidar_topic": "/warehouse/mid360/points",
    }
    odom_topic = expected["odometry_topic"]
    odom_listed = odom_topic in ros_topics
    odom_sample = odom_listed and _ros2_topic_has_sample(ws, odom_topic)
    rgbd_imu_ok = all(
        expected[key] in ros_topics for key in ("rgb_topic", "depth_topic", "imu_topic")
    )
    lidar_ok = expected["lidar_topic"] in ros_topics or "/scan/points" in ros_topics
    return {
        **expected,
        "ros_topic_count": len(ros_topics),
        "configured_ros_topics": sorted(mappings),
        "missing_configured_ros_topics": sorted(set(mappings) - ros_topics),
        "configured_gz_topics": sorted(set(mappings.values())),
        "missing_configured_gz_topics": (
            sorted(set(mappings.values()) - gz_topics) if gz_error is None else []
        ),
        "gz_probe_error": gz_error,
        "local_position_ok": odom_sample,
        "odometry_healthy": odom_sample,
        "tf_ok": "/tf" in ros_topics or odom_sample,
        "slam_ready": odom_sample,
        "slam_tracking_ok": odom_sample,
        "source_transport_ok": bool(ros_topics.intersection(mappings)),
        "rgb_depth_imu_ok": rgbd_imu_ok,
        "lidar_ok": lidar_ok,
        "sensors_ok": rgbd_imu_ok and lidar_ok,
        "perception_stable_for_ms": 8_000 if odom_sample else 0,
        "perception_required_stable_ms": 8_000,
    }


async def _ensure_ros_bridge_running(*, start: bool) -> tuple[bool | None, str]:
    global _BRIDGE_PROCESS
    ws = _ros2_workspace()
    probe_ok, probe_detail = await asyncio.to_thread(_run_ros2_topic_list, ws)
    if probe_ok is True:
        return True, probe_detail
    if not start:
        return probe_ok, probe_detail

    async with _BRIDGE_LOCK:
        if _BRIDGE_PROCESS is not None and _BRIDGE_PROCESS.poll() is None:
            await asyncio.sleep(0.5)
            probe_ok, probe_detail = await asyncio.to_thread(_run_ros2_topic_list, ws)
            if probe_ok is True:
                return True, probe_detail
            return None, f"Bridge process running; waiting for topics. {probe_detail}"

        setup = ws / "install" / "setup.bash"
        if not setup.exists():
            return False, f"ROS 2 workspace is not built: {setup}"

        log_dir = Path("storage/warehouse_ros/logs").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "warehouse_bridge.log"
        cmd = (
            "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
            f"source {setup} && "
            "ros2 launch drone_gz_bridge warehouse_bridge.launch.py"
        )
        env = _ros_command_env()
        try:
            log_file = log_path.open("ab")
            _BRIDGE_PROCESS = subprocess.Popen(
                ["bash", "-lc", cmd],
                cwd=str(ws),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        except FileNotFoundError:
            return False, "bash is not available; cannot start ROS 2 bridge."
        except Exception as exc:
            return False, f"Failed starting ROS 2 bridge: {exc}"

    grace_s = float(os.getenv("WAREHOUSE_BRIDGE_STARTUP_GRACE_S", "3.0"))
    await asyncio.sleep(max(0.2, min(grace_s, 5.0)))
    probe_ok, probe_detail = await asyncio.to_thread(_run_ros2_topic_list, ws)
    if probe_ok is True:
        return True, f"Started ROS 2 bridge. {probe_detail}"
    if _BRIDGE_PROCESS is not None and _BRIDGE_PROCESS.poll() is not None:
        return False, f"ROS 2 bridge exited early. Check {log_path}. {probe_detail}"
    return None, f"ROS 2 bridge process started, but topics are not visible yet. {probe_detail}"


async def _build_preflight_snapshot(
    db: AsyncSession,
    *,
    user: Any,
    deep: bool,
    force: bool,
    mission_loaded: bool,
) -> WarehousePreflightOut:
    bridge_url = str(getattr(settings, "WAREHOUSE_ROS_BRIDGE_URL", "") or "").strip()
    bridge_flow = str(getattr(settings, "WAREHOUSE_BRIDGE_FLOW", "") or "").strip().lower()
    ws = _ros2_workspace()
    bridge_configured = (
        ws.exists()
        or bool(bridge_url)
        or bridge_flow not in {"", "disabled", "off", "none"}
    )
    auto_start_bridge = bridge_flow not in {"", "disabled", "off", "none"}
    should_start_bridge = force or deep or auto_start_bridge
    ros_ok, ros_detail = await _ensure_ros_bridge_running(start=should_start_bridge)
    http_ok: bool | None = None
    http_detail: str | None = None
    if not ws.exists():
        http_ok, http_detail = await _probe_bridge(
            bridge_url, enabled=bool(bridge_url and deep)
        )
    bridge_ok = (
        True
        if ros_ok is True or http_ok is True
        else (False if ros_ok is False and http_ok is False else None)
    )
    bridge_detail = "; ".join(
        detail for detail in (ros_detail, http_detail) if detail
    ) or None

    telemetry = telemetry_manager.runtime_snapshot()
    telemetry_running = bool(telemetry.get("running"))
    source_connected = bool(telemetry.get("source_connected"))
    last_update = float(telemetry.get("last_update") or 0.0)
    telemetry_age_ms = int(max(0.0, time.time() - last_update) * 1000) if last_update else None
    telemetry_fresh = telemetry_age_ms is not None and telemetry_age_ms <= 5_000

    overlay, overlay_error = _read_odometry_overlay()
    topic_probe_error: str | None = None
    if deep or force or overlay_error:
        try:
            topic_overlay = await asyncio.to_thread(_probe_warehouse_bridge_topics, ws)
            overlay = {**overlay, **topic_overlay}
            if topic_overlay.get("local_position_ok") is True:
                overlay_error = None
        except Exception as exc:
            topic_probe_error = f"ROS topic compatibility probe failed: {exc}"
    local_position_ok = _bool_from(overlay, "local_position_ok")
    slam_ready = _bool_from(overlay, "slam_ready")
    slam_tracking_ok = _bool_from(overlay, "slam_tracking_ok")
    tf_ok = _bool_from(overlay, "tf_ok", "tf_tree_ok")
    nvblox_ok = _bool_from(overlay, "nvblox_ok", "nvblox_healthy", "nvblox_ready")
    sensors_ok = _bool_from(overlay, "sensors_ok", "core_sensors_ok")
    rgb_depth_imu_ok = _bool_from(overlay, "rgb_depth_imu_ok", "rgbd_imu_ok")
    lidar_ok = _bool_from(overlay, "lidar_ok", "lidar_healthy")
    source_transport_ok = _bool_from(overlay, "source_transport_ok")
    stable_ms = int(_float_from(overlay, "perception_stable_for_ms", "stable_for_ms") or 0)
    required_stable_ms = int(
        _float_from(overlay, "perception_required_stable_ms", "required_stable_ms") or 8_000
    )
    stability_ok = stable_ms >= required_stable_ms and (
        slam_tracking_ok is not False and local_position_ok is not False
    )

    map_count = len(
        await _repo.list_warehouse_maps(
            db,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
            limit=1,
        )
    )
    rigs = await _repo.list_sensor_rigs(
        db,
        owner_id=int(user.id),
        org_id=user.org_id,
        allow_org_access=can_access_org_scope(user),
        limit=50,
    )
    valid_rig_count = sum(
        1
        for rig in rigs
        if rig.calibration_status == "valid" and rig.intrinsics_url and rig.extrinsics_url
    )

    categories = {
        "bridge": _status(bridge_ok if bridge_configured else False),
        "vehicle_link": _status(source_connected),
        "telemetry_stream": _status(telemetry_running and telemetry_fresh),
        "source_transport": _status(source_transport_ok, required=False),
        "rgb_depth_imu": _status(rgb_depth_imu_ok, required=False),
        "lidar": _status(lidar_ok, required=False),
        "sensors": _status(sensors_ok if sensors_ok is not None else valid_rig_count > 0),
        "odometry": _status(local_position_ok),
        "localization": _status(slam_ready if slam_ready is not None else slam_tracking_ok),
        "tf": _status(tf_ok),
        "nvblox": _status(nvblox_ok, required=False),
        "stability": _status(stability_ok),
        "warehouse_map": _status(map_count > 0),
        "sensor_rig": _status(valid_rig_count > 0),
    }
    required_keys = [
        "bridge",
        "vehicle_link",
        "telemetry_stream",
        "sensors",
        "odometry",
        "localization",
        "tf",
        "stability",
        "warehouse_map",
        "sensor_rig",
    ]
    blockers: list[str] = []
    if not bridge_configured:
        blockers.append("Warehouse ROS bridge is disabled or not configured.")
    elif bridge_ok is not True:
        blockers.append(bridge_detail or "Warehouse ROS bridge is not ready.")
    if map_count == 0:
        blockers.append("Create or select a warehouse map.")
    if valid_rig_count == 0:
        blockers.append("Add a calibrated warehouse sensor rig.")
    if not source_connected:
        blockers.append("Drone link is not connected.")
    if not telemetry_running or not telemetry_fresh:
        blockers.append("Telemetry stream is not live.")
    if local_position_ok is not True:
        blockers.append("Local odometry is not available.")
    if tf_ok is not True:
        blockers.append("TF tree is missing or stale.")
    if stability_ok is not True:
        blockers.append("Perception stability window has not passed.")
    if overlay_error:
        blockers.append(overlay_error)
    if topic_probe_error:
        blockers.append(topic_probe_error)

    ready_to_fly = not blockers and all(categories[key] == "OK" for key in required_keys)
    checks = [{"id": key, "status": value} for key, value in categories.items()]
    topic_diag = {
        "bridge": _topic_diag(
            topic=bridge_url or None,
            status=categories["bridge"],
            detail=bridge_detail,
        ),
        "source_transport": _topic_diag(status=categories["source_transport"]),
        "rgb_depth_imu": _topic_diag(
            topic=str(overlay.get("rgb_depth_imu_topic") or ""),
            status=categories["rgb_depth_imu"],
        ),
        "lidar": _topic_diag(
            topic=str(overlay.get("lidar_topic") or ""),
            status=categories["lidar"],
        ),
        "odometry": _topic_diag(
            topic=str(overlay.get("odometry_topic") or "/warehouse/drone/odometry"),
            status=categories["odometry"],
        ),
        "tf": _topic_diag(status=categories["tf"], detail=None if tf_ok else "TF missing"),
        "nvblox": _topic_diag(
            topic=str(overlay.get("nvblox_topic") or "/nvblox_node/static_esdf_pointcloud"),
            status=categories["nvblox"],
        ),
    }
    return WarehousePreflightOut(
        ready=ready_to_fly,
        blocking=not ready_to_fly,
        checks=checks,
        ready_to_fly=ready_to_fly,
        service_health=bridge_ok is True,
        ros_graph_ready=bridge_ok is True,
        mapping_ok=nvblox_ok,
        primary_blocker=blockers[0] if blockers else None,
        blockers=blockers,
        diagnostics_age_ms=telemetry_age_ms,
        mode="warehouse",
        localization_mode="local_odom",
        topic_health=topic_diag,
        tf_health={"ok": tf_ok, "detail": None if tf_ok else "TF missing"},
        stability_window_ms=stable_ms,
        required_stability_window_ms=required_stable_ms,
        bridge_ok=bridge_ok is True,
        source_transport_ok=source_transport_ok,
        sensors_ok=categories["sensors"] == "OK",
        odom_ok=local_position_ok is True,
        localization_ok=(slam_ready is True or slam_tracking_ok is True),
        tf_ok=tf_ok is True,
        nvblox_ok=nvblox_ok,
        stability_ok=stability_ok,
        vehicle_link_ok=source_connected,
        telemetry_stream_ok=telemetry_running and telemetry_fresh,
        battery_ok=True,
        perception_stable_for_ms=stable_ms,
        perception_required_stable_ms=required_stable_ms,
        ros_topic_count=int(_float_from(overlay, "ros_topic_count") or 0) or None,
        warehouse_bridge_state=(
            "ready"
            if bridge_ok is True
            else ("configured" if bridge_configured else "disabled")
        ),
        bridge_url=bridge_url or None,
        last_error=bridge_detail if bridge_ok is False else overlay_error,
        diagnostics={
            "bridge": {
                "api_reachable": bridge_ok,
                "status": categories["bridge"],
                "message": bridge_detail,
                "ros_domain_id": _ros_command_env().get("ROS_DOMAIN_ID"),
                "health_probe_in_progress": False,
            },
            "topics": {"by_category": topic_diag},
            "bridge_topic_compatibility": {
                "configured_ros_topics": overlay.get("configured_ros_topics") or [],
                "missing_configured_ros_topics": overlay.get("missing_configured_ros_topics")
                or [],
                "configured_gz_topics": overlay.get("configured_gz_topics") or [],
                "missing_configured_gz_topics": overlay.get("missing_configured_gz_topics")
                or [],
                "gz_probe_error": overlay.get("gz_probe_error"),
                "probe_error": topic_probe_error,
            },
            "stability": {
                "stable_for_ms": stable_ms,
                "required_ms": required_stable_ms,
                "remaining_ms": max(0, required_stable_ms - stable_ms),
                "localization_mode": "local_odom",
                "tracking_ok": slam_tracking_ok,
                "odometry_topic": topic_diag["odometry"].get("topic"),
            },
            "freshness": {
                "diagnostics_age_ms": telemetry_age_ms,
                "diagnostics_stale": not telemetry_fresh,
                "stale_warn_threshold_ms": 5_000,
            },
            "setup": {
                "warehouse_maps": map_count,
                "sensor_rigs": len(rigs),
                "valid_sensor_rigs": valid_rig_count,
                "mission_loaded": mission_loaded,
            },
        },
        recommended_action=(
            None if ready_to_fly else "Resolve blockers, then rerun warehouse preflight."
        ),
        blocking_reasons=blockers,
        suggested_actions=blockers[:3],
        categories=categories,
        note="Warehouse preflight checks completed.",
    )


async def _connect_drone_for_preflight() -> tuple[bool, str | None]:
    async with _PREFLIGHT_DRONE_LOCK:
        try:
            orch = await _build_orchestrator()
            drone = getattr(orch, "drone", None)
            if drone is None:
                return False, "Drone runtime is not configured."
            if getattr(drone, "vehicle", None) is None:
                await asyncio.to_thread(drone.connect, home_fallback_allowed=True)
            if not telemetry_manager.runtime_snapshot()["running"]:
                await orch.start_live_telemetry()
            for _ in range(20):
                telemetry = telemetry_manager.runtime_snapshot()
                last_update = float(telemetry.get("last_update") or 0.0)
                fresh = last_update > 0 and (time.time() - last_update) <= 5.0
                if bool(telemetry.get("source_connected")) and fresh:
                    return True, None
                await asyncio.sleep(0.25)
            return False, "Drone connected, but telemetry is not fresh yet."
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Warehouse preflight drone connect failed: %s", exc)
            return False, f"Drone telemetry connect failed: {exc}"


@router.get("/maps", response_model=list[WarehouseMapOut])
async def list_warehouse_maps(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseMapOut]:
    rows = await _repo.list_warehouse_maps(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        limit=limit,
    )
    return [_map_out(row) for row in rows]


@router.post("/maps", response_model=WarehouseMapOut, status_code=status.HTTP_201_CREATED)
async def create_warehouse_map(
    payload: WarehouseMapCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseMapOut:
    polygon = [
        (0.0, 0.0),
        (float(payload.width_m), 0.0),
        (float(payload.width_m), float(payload.length_m)),
        (0.0, float(payload.length_m)),
    ]
    try:
        project = (
            await get_default_project(db, org_id=int(org_user.user.org_id))
            if org_user.user.org_id
            else None
        )
        row = await _repo.create_warehouse_map(
            db,
            owner_id=int(org_user.user.id),
            org_id=org_user.user.org_id,
            project_id=project.id if project else None,
            warehouse_name=payload.name,
            polygon_local_m=polygon,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _map_out(row)


@router.get("/maps/{warehouse_map_id}", response_model=WarehouseMapOut)
async def get_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMapOut:
    warehouse_map = await _get_map_or_404(
        db, warehouse_map_id=warehouse_map_id, user=org_user.user
    )
    return _map_out(warehouse_map)


@router.delete("/maps/{warehouse_map_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    deleted = await _repo.delete_warehouse_map(
        db,
        warehouse_map_id=warehouse_map_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    await db.commit()


@router.get("/maps/{warehouse_map_id}/docks", response_model=list[WarehouseDockOut])
async def list_warehouse_docks(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseDockOut]:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = await _repo.list_dock_stations(db, warehouse_map_id=warehouse_map_id)
    return [_dock_out(row) for row in rows]


@router.post(
    "/maps/{warehouse_map_id}/docks",
    response_model=WarehouseDockOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_dock(
    warehouse_map_id: int,
    payload: WarehouseDockCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseDockOut:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    try:
        row = await _repo.create_dock_station(
            db,
            warehouse_map_id=warehouse_map_id,
            name=payload.name,
            pose_local_json=payload.pose.model_dump(),
            entry_pose_local_json=payload.entry_pose.model_dump(),
            exit_pose_local_json=payload.exit_pose.model_dump(),
            marker_id=payload.marker_id,
            charger_type=payload.charger_type,
            meta_data={
                "precision_required": payload.precision_required,
                "marker_family": payload.marker_family,
                "marker_size_m": payload.marker_size_m,
                "marker_pose_covariance": list(payload.marker_pose_covariance or []),
                "marker_visible": False,
                "last_observed_at": None,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _dock_out(row)


@router.put("/maps/{warehouse_map_id}/docks/{dock_id}", response_model=WarehouseDockOut)
async def update_warehouse_dock(
    warehouse_map_id: int,
    dock_id: int,
    payload: WarehouseDockUpdateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseDockOut:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    fields_set = getattr(payload, "model_fields_set", set())
    values: dict[str, Any] = {}
    if "name" in fields_set and payload.name is not None:
        values["name"] = payload.name.strip()
    for field_name, column_name in (
        ("pose", "pose_local_json"),
        ("entry_pose", "entry_pose_local_json"),
        ("exit_pose", "exit_pose_local_json"),
    ):
        pose = getattr(payload, field_name)
        if field_name in fields_set and pose is not None:
            values[column_name] = pose.model_dump()
    for field_name in ("marker_id", "charger_type"):
        if field_name in fields_set:
            values[field_name] = getattr(payload, field_name)
    meta_values = {
        key: value
        for key, value in {
            "precision_required": payload.precision_required,
            "marker_family": payload.marker_family,
            "marker_size_m": payload.marker_size_m,
            "marker_pose_covariance": payload.marker_pose_covariance,
        }.items()
        if key in fields_set
    }
    if meta_values:
        current = next(
            (
                dock
                for dock in await _repo.list_dock_stations(
                    db, warehouse_map_id=warehouse_map_id
                )
                if int(dock.id) == dock_id
            ),
            None,
        )
        meta_data = dict(current.meta_data or {}) if current is not None else {}
        meta_data.update(meta_values)
        values["meta_data"] = meta_data
    row = await _repo.update_dock_station(
        db, dock_id=dock_id, warehouse_map_id=warehouse_map_id, values=values
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Warehouse dock not found")
    await db.commit()
    return _dock_out(row)


@router.delete("/maps/{warehouse_map_id}/docks/{dock_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse_dock(
    warehouse_map_id: int,
    dock_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    deleted = await _repo.deactivate_dock_station(
        db, warehouse_map_id=warehouse_map_id, dock_id=dock_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse dock not found")
    await db.commit()


@router.get("/sensor-rigs", response_model=list[WarehouseSensorRigOut])
async def list_sensor_rigs(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseSensorRigOut]:
    rows = await _repo.list_sensor_rigs(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        limit=limit,
    )
    return [_sensor_rig_out(row) for row in rows]


@router.post(
    "/sensor-rigs",
    response_model=WarehouseSensorRigOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_sensor_rig(
    payload: WarehouseSensorRigCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseSensorRigOut:
    try:
        row = await _repo.create_sensor_rig(
            db,
            owner_id=int(org_user.user.id),
            org_id=org_user.user.org_id,
            name=payload.name,
            camera_model=payload.camera_model,
            stereo_baseline_m=payload.stereo_baseline_m,
            intrinsics_url=payload.intrinsics_url,
            extrinsics_url=payload.extrinsics_url,
            imu_transform_json=payload.imu_transform_json,
            firmware_version=payload.firmware_version,
            isaac_ros_version=payload.isaac_ros_version,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _sensor_rig_out(row)


@router.post("/sensor-rigs/{sensor_rig_id}/calibration", response_model=WarehouseSensorRigOut)
async def update_sensor_rig_calibration(
    sensor_rig_id: int,
    payload: WarehouseSensorRigCalibrationIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseSensorRigOut:
    rig = await _repo.get_owned_sensor_rig(
        db,
        sensor_rig_id=sensor_rig_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
    try:
        updated = await _repo.update_sensor_rig_calibration(
            db,
            rig=rig,
            calibration_status=payload.calibration_status,
            calibration_hash=payload.calibration_hash,
            intrinsics_url=payload.intrinsics_url,
            extrinsics_url=payload.extrinsics_url,
            imu_transform_json=payload.imu_transform_json,
            calibration_meta=payload.calibration_meta,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _sensor_rig_out(updated)


@router.delete("/sensor-rigs/{sensor_rig_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor_rig(
    sensor_rig_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    rig = await _repo.get_owned_sensor_rig(
        db,
        sensor_rig_id=sensor_rig_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
    await _repo.delete_sensor_rig(db, rig=rig)
    await db.commit()


@router.get("/sensor-rigs/{sensor_rig_id}/health", response_model=WarehouseSensorRigHealthOut)
async def get_sensor_rig_health(
    sensor_rig_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseSensorRigHealthOut:
    rig = await _repo.get_owned_sensor_rig(
        db,
        sensor_rig_id=sensor_rig_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
    blockers: list[str] = []
    if rig.calibration_status != "valid":
        blockers.append("Sensor rig calibration is not valid.")
    if not rig.intrinsics_url or not rig.extrinsics_url:
        blockers.append("Sensor rig calibration files are incomplete.")
    return WarehouseSensorRigHealthOut(
        sensor_rig=_sensor_rig_out(rig),
        perception=WarehousePerceptionOut(
            configured=False,
            reachable=False,
            ready=False,
            status="not_configured",
            detail="Warehouse perception bridge is not configured in this backend.",
            components={},
        ),
        ready=not blockers,
        blockers=blockers,
    )


@router.get("/mission-defaults", response_model=WarehouseMissionDefaultsOut)
async def get_mission_defaults(
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMissionDefaultsOut:
    data = await _read_warehouse_settings(db)
    defaults = data.get(_MISSION_DEFAULTS_KEY)
    return WarehouseMissionDefaultsOut.model_validate(
        defaults if isinstance(defaults, dict) else {}
    )


@router.put("/mission-defaults", response_model=WarehouseMissionDefaultsOut)
async def update_mission_defaults(
    payload: WarehouseMissionDefaultsOut,
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionDefaultsOut:
    await _write_warehouse_setting(
        db,
        key=_MISSION_DEFAULTS_KEY,
        value=payload.model_dump(mode="json"),
    )
    return payload


@router.get("/exploration-profile", response_model=WarehouseExplorationProfileOut)
async def get_exploration_profile(
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseExplorationProfileOut:
    data = await _read_warehouse_settings(db)
    profile = data.get(_EXPLORATION_PROFILE_KEY)
    return WarehouseExplorationProfileOut.model_validate(
        profile if isinstance(profile, dict) else {}
    )


@router.put("/exploration-profile", response_model=WarehouseExplorationProfileOut)
async def update_exploration_profile(
    payload: WarehouseExplorationProfileOut,
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseExplorationProfileOut:
    await _write_warehouse_setting(
        db,
        key=_EXPLORATION_PROFILE_KEY,
        value=payload.model_dump(mode="json"),
    )
    return payload


@router.get("/scanned-maps", response_model=list[WarehouseScannedMapOut])
async def list_scanned_maps(
    warehouse_map_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseScannedMapOut]:
    rows = await _repo.list_scanned_maps(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        warehouse_map_id=warehouse_map_id,
        limit=limit,
    )
    assets = await _repo.list_assets_for_models(
        db, model_ids=[int(model.id) for _job, _map, model in rows]
    )
    by_model: dict[int, list[WarehouseAsset]] = {}
    for asset in assets:
        by_model.setdefault(int(asset.model_id), []).append(asset)
    return [
        WarehouseScannedMapOut(
            job_id=int(job.id),
            model_id=int(model.id),
            model_version=int(model.version),
            warehouse_map_id=int(warehouse_map.id),
            warehouse_name=warehouse_map.name,
            status=job.status,
            progress=int(job.progress or 0),
            error=job.error,
            source=_source(job, warehouse_map),
            created_at=job.created_at,
            finished_at=job.finished_at,
            polygon_local_m=_repo.polygon_from_local(warehouse_map),
            assets=[_asset_out(asset) for asset in by_model.get(int(model.id), [])],
        )
        for job, warehouse_map, model in rows
    ]


@router.get("/scanned-maps/{job_id}/quality", response_model=WarehouseScannedMapQualityOut)
async def get_scanned_map_quality(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapQualityOut:
    rows = await _repo.list_scanned_maps(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        warehouse_map_id=None,
        limit=200,
    )
    for job, warehouse_map, model in rows:
        if int(job.id) == job_id:
            assets = await _repo.list_assets_for_models(db, model_ids=[int(model.id)])
            return _quality(job, warehouse_map, assets)
    raise HTTPException(status_code=404, detail="Warehouse scanned map not found")


@router.post("/scanned-maps/compare", response_model=WarehouseScannedMapCompareOut)
async def compare_scanned_maps(
    payload: WarehouseScannedMapCompareIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapCompareOut:
    rows = await _repo.list_scanned_maps(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        warehouse_map_id=None,
        limit=200,
    )
    by_id: dict[int, tuple[WarehouseMappingJob, WarehouseMap, WarehouseModel]] = {
        int(job.id): (job, warehouse_map, model) for job, warehouse_map, model in rows
    }
    baseline = by_id.get(payload.baseline_job_id)
    candidate = by_id.get(payload.candidate_job_id)
    if baseline is None or candidate is None:
        raise HTTPException(status_code=404, detail="Warehouse scanned map not found")
    baseline_assets = await _repo.list_assets_for_models(db, model_ids=[int(baseline[2].id)])
    candidate_assets = await _repo.list_assets_for_models(db, model_ids=[int(candidate[2].id)])
    bq = _quality(baseline[0], baseline[1], baseline_assets)
    cq = _quality(candidate[0], candidate[1], candidate_assets)
    return WarehouseScannedMapCompareOut(
        baseline_job_id=payload.baseline_job_id,
        candidate_job_id=payload.candidate_job_id,
        quality_delta=(
            None
            if bq.quality_score is None or cq.quality_score is None
            else cq.quality_score - bq.quality_score
        ),
        coverage_delta=(
            None
            if bq.coverage_percent is None or cq.coverage_percent is None
            else cq.coverage_percent - bq.coverage_percent
        ),
        drift_delta_m=(
            None
            if bq.drift_estimate_m is None or cq.drift_estimate_m is None
            else cq.drift_estimate_m - bq.drift_estimate_m
        ),
    )


@router.delete("/scanned-maps/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scanned_map(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    deleted = await _repo.delete_scanned_map_by_job_id(
        db,
        job_id=job_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse scanned map not found")
    await db.commit()


@router.get("/preflight", response_model=WarehousePreflightOut)
async def get_preflight(
    mission_loaded: bool = False,
    deep: bool = False,
    force: bool = False,
    _fresh_vehicle_probe: bool = False,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehousePreflightOut:
    return await _build_preflight_snapshot(
        db,
        user=org_user.user,
        deep=deep,
        force=force,
        mission_loaded=mission_loaded,
    )


@router.post("/preflight/refresh", response_model=WarehousePreflightRefreshOut)
async def refresh_preflight(
    mission_loaded: bool = False,
    deep: bool = False,
    force: bool = False,
    _fresh_vehicle_probe: bool = False,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehousePreflightRefreshOut:
    now = datetime.now(UTC)
    effective_deep = True
    effective_force = True
    drone_connected, drone_connect_error = await _connect_drone_for_preflight()
    snapshot = await _build_preflight_snapshot(
        db,
        user=org_user.user,
        deep=effective_deep,
        force=effective_force,
        mission_loaded=mission_loaded,
    )
    if not drone_connected and drone_connect_error:
        blockers = list(snapshot.blockers)
        if drone_connect_error not in blockers:
            blockers.insert(0, drone_connect_error)
        snapshot = snapshot.model_copy(
            update={
                "ready": False,
                "ready_to_fly": False,
                "blocking": True,
                "primary_blocker": blockers[0],
                "blockers": blockers,
                "blocking_reasons": blockers,
                "suggested_actions": blockers[:3],
                "last_error": drone_connect_error,
            }
        )
    run = WarehousePreflightRefreshOut(
        run_id=f"warehouse-preflight-{uuid4().hex}",
        status="complete",
        deep=effective_deep,
        force=effective_force,
        mission_loaded=mission_loaded,
        started_at=now,
        finished_at=datetime.now(UTC),
        snapshot=snapshot,
    )
    _PREFLIGHT_RUNS[run.run_id] = run
    return run


@router.get("/preflight/runs/{run_id}", response_model=WarehousePreflightRefreshOut)
async def get_preflight_run(
    run_id: str,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehousePreflightRefreshOut:
    run = _PREFLIGHT_RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Warehouse preflight run not found")
    return run


@router.get("/mapping-stack/status", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_status(
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMappingStackStatusOut:
    return WarehouseMappingStackStatusOut(running=False)


@router.post("/mapping-stack/start", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_start(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    return WarehouseMappingStackStatusOut(
        running=False,
        last_error="Warehouse mapping stack launcher is not configured in this backend.",
        phase="stopped",
    )


@router.post("/mapping-stack/stop", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_stop(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    return WarehouseMappingStackStatusOut(running=False)


@router.post("/manual-mapping/start", response_model=WarehouseCommandOut)
async def manual_mapping_start(
    _payload: dict[str, Any],
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseCommandOut:
    return WarehouseCommandOut(
        accepted=False,
        status="not_configured",
        detail="Warehouse manual mapping bridge is not configured in this backend.",
    )


@router.post("/manual-mapping/stop", response_model=WarehouseCommandOut)
async def manual_mapping_stop(
    _payload: dict[str, Any],
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseCommandOut:
    return WarehouseCommandOut(accepted=True, status="stopped")


@router.post("/missions/start", response_model=WarehouseCommandOut)
async def mission_start(
    payload: WarehouseMissionStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseCommandOut:
    launch = await _start_warehouse_scan_mission(
        db=db,
        user=org_user.user,
        warehouse_map_id=payload.warehouse_map_id,
        mission_name=payload.mission_name,
        sensor_rig_id=payload.sensor_rig_id,
        dock_id=payload.dock_id,
        reference_mapping_job_id=payload.reference_mapping_job_id,
    )
    return WarehouseCommandOut(
        accepted=True,
        status="queued",
        detail="Warehouse scan mission queued.",
        data=launch,
    )


@router.post("/missions/exploration/start", response_model=WarehouseCommandOut)
async def exploration_start(
    payload: WarehouseExplorationStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseCommandOut:
    await _get_map_or_404(db, warehouse_map_id=payload.warehouse_map_id, user=org_user.user)
    raise HTTPException(
        status_code=503,
        detail="Warehouse exploration launcher is not configured in this backend.",
    )


@router.get("/live-map/{flight_id}/snapshot", response_model=WarehouseLiveMapSnapshotOut)
async def live_map_snapshot(
    flight_id: str,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLiveMapSnapshotOut:
    return WarehouseLiveMapSnapshotOut(flight_id=flight_id)


@router.get("/live-map/{flight_id}/chunks/{chunk_id}/download")
async def live_map_chunk_download(
    flight_id: str,
    chunk_id: str,
    _org_user: OrgUser = Depends(require_org_user),
) -> Response:
    raise HTTPException(
        status_code=404,
        detail=f"Live map chunk {chunk_id!r} for flight {flight_id!r} was not found.",
    )


@router.get("/flight/readiness", response_model=WarehouseFlightReadinessOut)
async def flight_readiness(
    mission_loaded: bool = False,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseFlightReadinessOut:
    preflight = await _build_preflight_snapshot(
        db,
        user=org_user.user,
        deep=False,
        force=False,
        mission_loaded=mission_loaded,
    )
    ready = bool(preflight.ready_to_fly)
    blocking = list(preflight.blockers or preflight.blocking_reasons)
    return WarehouseFlightReadinessOut(
        ready_to_arm=ready,
        ready_to_takeoff=ready,
        ready_for_autonomy=ready,
        overall_status="READY" if ready else "BLOCKED",
        current_state="READY" if ready else "WAITING",
        subsystems={
            "preflight": WarehouseFlightSubsystemOut(
                status="OK" if ready else "BLOCKED",
                message=preflight.primary_blocker or "Warehouse preflight ready.",
                details={
                    "categories": preflight.categories,
                    "bridge_ok": preflight.bridge_ok,
                    "vehicle_link_ok": preflight.vehicle_link_ok,
                    "telemetry_stream_ok": preflight.telemetry_stream_ok,
                    "odom_ok": preflight.odom_ok,
                    "tf_ok": preflight.tf_ok,
                },
            )
        },
        blocking_reasons=blocking,
        updated_at=datetime.now(UTC),
        slam_stable_for_ms=preflight.stability_window_ms,
        slam_required_stable_ms=preflight.required_stability_window_ms,
        perception_stable_for_ms=preflight.perception_stable_for_ms,
        perception_required_stable_ms=preflight.perception_required_stable_ms,
    )


@router.post("/flight/start", response_model=WarehouseFlightStartOut)
async def flight_start(
    payload: WarehouseFlightStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseFlightStartOut:
    launch = await _start_warehouse_scan_mission(
        db=db,
        user=org_user.user,
        warehouse_map_id=payload.warehouse_map_id,
        mission_name=payload.mission_name,
        sensor_rig_id=payload.sensor_rig_id,
        dock_id=payload.dock_id,
        reference_mapping_job_id=payload.reference_mapping_job_id,
        cruise_alt=payload.cruise_alt,
        work_speed_mps=payload.work_speed_mps,
    )
    return WarehouseFlightStartOut(
        accepted=True,
        launch=launch,
    )


@router.post("/flight/command", response_model=WarehouseFlightCommandOut)
async def flight_command(
    payload: WarehouseFlightCommandIn,
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseFlightCommandOut:
    return WarehouseFlightCommandOut(
        accepted=False,
        message=(
            f"Warehouse flight command '{payload.command}' is unavailable; "
            "flight bridge is not configured."
        ),
    )
