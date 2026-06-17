from __future__ import annotations

import asyncio
import hmac
import json
import logging
import shlex
import subprocess
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse, StreamingResponse

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.entrypoints.cli.run_mission import _build_orchestrator
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.infrastructure.warehouse.bridge_config import (
    missing_critical_topic_blockers,
    probe_bridge_topics,
    quick_ros_bridge_check,
    ros_command_env,
)
from backend.modules.identity.dependencies import (
    OrgUser,
    require_mission_exec,
    require_org_user,
    require_org_write,
)
from backend.modules.missions.api.routes import (
    MissionCreateIn,
    MissionCreateOut,
    _build_mission,
    create_mission,
)
from backend.modules.missions.flight_profile import FlightEnvironment
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.organizations.service import can_access_org_scope, get_default_project
from backend.modules.preflight.checks.schemas import CheckStatus
from backend.modules.telemetry.websocket_api import _authorize_websocket
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseDockStation,
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.repository.settings import WarehouseSettingsRepository
from backend.modules.warehouse.schemas import (
    WarehouseInspectionMissionCreate,
    WarehouseInspectionMissionRead,
    WarehouseInspectionResultRead,
    WarehouseScanPoseComputeIn,
    WarehouseScanPoseComputeOut,
    WarehouseScanTargetCreate,
    WarehouseScanTargetImport,
    WarehouseScanTargetRead,
    WarehouseScanTargetUpdate,
)
from backend.modules.warehouse.service.inspection import (
    MockWarehouseScanner,
    build_inspection_waypoints,
    compute_scan_pose,
    order_targets,
)
from backend.modules.warehouse.service.live_map_replay import (
    build_disk_live_map_snapshot,
    resolve_client_flight_id_for_scan_job,
)
from backend.modules.warehouse.service.live_map_storage import (
    LiveMapStorageError,
    warehouse_live_map_chunk_storage,
)
from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveMapSnapshot,
    normalize_live_map_payload,
    warehouse_live_map_stream,
)
from backend.modules.warehouse.service.warehouse_preflight import (
    apply_ros_preflight_gate,
    default_warehouse_scan_preflight_mission_data,
    run_warehouse_ros_preflight_report,
    warehouse_preflight_can_start,
    warehouse_preflight_failed_checks,
)
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

router = APIRouter(prefix="/warehouse", tags=["warehouse"])
logger = logging.getLogger(__name__)

_repo = WarehouseMappingRepository()
_settings_repo = WarehouseSettingsRepository()
_PREFLIGHT_RUNS: OrderedDict[str, WarehousePreflightRefreshOut] = OrderedDict()
_PREFLIGHT_RUNS_MAX = 50
_PREFLIGHT_RUNS_TTL_S = 60 * 60
_BRIDGE_PROCESS: subprocess.Popen[bytes] | None = None
_BRIDGE_LOCK = asyncio.Lock()
_PREFLIGHT_DRONE_LOCK = asyncio.Lock()
_SETTINGS_SECTION = "warehouse"
_MISSION_DEFAULTS_KEY = "mission_defaults"
_EXPLORATION_PROFILE_KEY = "exploration_profile"


def _remember_preflight_run(run: WarehousePreflightRefreshOut) -> None:
    """Keep recent preflight refresh results bounded in memory."""
    now = datetime.now(UTC)
    _PREFLIGHT_RUNS[run.run_id] = run
    _PREFLIGHT_RUNS.move_to_end(run.run_id)
    stale_keys = [
        key
        for key, value in _PREFLIGHT_RUNS.items()
        if (now - value.started_at).total_seconds() > _PREFLIGHT_RUNS_TTL_S
    ]
    for key in stale_keys:
        _PREFLIGHT_RUNS.pop(key, None)
    while len(_PREFLIGHT_RUNS) > _PREFLIGHT_RUNS_MAX:
        _PREFLIGHT_RUNS.popitem(last=False)


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
    warning: str | None = None
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


class WarehouseMissionLaunchPreflightOut(BaseModel):
    preflight_run_id: str = ""
    overall_status: str = "PASS"
    can_start_mission: bool = True


class WarehouseMissionLaunchOut(BaseModel):
    warehouse_map_id: int
    warehouse_name: str
    preflight: WarehouseMissionLaunchPreflightOut
    mission: MissionCreateOut


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


class WarehouseLiveMapPublishOut(BaseModel):
    accepted: bool
    flight_id: str
    changed_chunk_count: int
    removed_chunk_count: int


class WarehouseLiveMapChunkUploadOut(BaseModel):
    accepted: bool
    flight_id: str
    chunk_id: str
    url: str
    byte_size: int
    checksum_sha256: str


# Upper bound on chunks fetched per batch request, to bound per-request work.
WAREHOUSE_LIVE_MAP_BATCH_MAX_CHUNKS = 256


class WarehouseLiveMapChunkBatchIn(BaseModel):
    chunk_ids: list[str] = Field(default_factory=list, max_length=WAREHOUSE_LIVE_MAP_BATCH_MAX_CHUNKS)


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


def _scan_target_out(row: WarehouseScanTarget) -> WarehouseScanTargetRead:
    return WarehouseScanTargetRead.model_validate(
        {
            "id": int(row.id),
            "warehouse_map_id": int(row.warehouse_map_id),
            "reference_model_id": row.reference_model_id,
            "dock_station_id": row.dock_station_id,
            "aisle_code": row.aisle_code,
            "rack_code": row.rack_code,
            "shelf_level": row.shelf_level,
            "bin_code": row.bin_code,
            "sku": row.sku,
            "barcode": row.barcode,
            "product_name": row.product_name,
            "target_point_local_json": row.target_point_local_json,
            "scan_pose_local_json": row.scan_pose_local_json,
            "shelf_normal_local_json": row.shelf_normal_local_json,
            "standoff_m": row.standoff_m,
            "hover_time_s": row.hover_time_s,
            "scan_timeout_s": row.scan_timeout_s,
            "priority": row.priority,
            "active": row.active,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _inspection_mission_out(row: WarehouseInspectionMission) -> WarehouseInspectionMissionRead:
    plan = row.plan_json if isinstance(row.plan_json, dict) else {}
    return WarehouseInspectionMissionRead.model_validate(
        {
            "id": int(row.id),
            "warehouse_map_id": int(row.warehouse_map_id),
            "name": row.name,
            "status": row.status,
            "scan_mode": row.scan_mode,
            "return_to_dock": row.return_to_dock,
            "target_ids": list(row.target_ids_json or []),
            "waypoints": list(plan.get("waypoints") or []),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _inspection_result_out(row: WarehouseInspectionResult) -> WarehouseInspectionResultRead:
    return WarehouseInspectionResultRead.model_validate(
        {
            "id": int(row.id),
            "mission_id": int(row.mission_id),
            "target_id": int(row.target_id),
            "status": row.status,
            "expected_barcode": row.expected_barcode,
            "detected_barcode": row.detected_barcode,
            "confidence": row.confidence,
            "image_asset_id": row.image_asset_id,
            "video_asset_id": row.video_asset_id,
            "drone_pose_local_json": row.drone_pose_local_json,
            "error_message": row.error_message,
            "scanned_at": row.scanned_at,
        }
    )


async def _get_scan_target_or_404(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    target_id: int,
    active_only: bool = False,
) -> WarehouseScanTarget:
    clauses = [
        WarehouseScanTarget.id == target_id,
        WarehouseScanTarget.warehouse_map_id == warehouse_map_id,
    ]
    if active_only:
        clauses.append(WarehouseScanTarget.active.is_(True))
    target = (await db.execute(select(WarehouseScanTarget).where(*clauses))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Warehouse scan target not found")
    return target


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


async def _get_scanned_map_row_or_404(
    db: AsyncSession,
    *,
    job_id: int,
    user: Any,
) -> tuple[WarehouseMappingJob, WarehouseMap, WarehouseModel]:
    scope = (
        or_(WarehouseMap.owner_id == int(user.id), WarehouseMap.org_id == user.org_id)
        if can_access_org_scope(user) and user.org_id is not None
        else WarehouseMap.owner_id == int(user.id)
    )
    # Use a direct indexed lookup instead of listing the latest 200 maps and scanning in Python.
    row = (
        await db.execute(
            select(WarehouseMappingJob, WarehouseMap, WarehouseModel)
            .join(WarehouseMap, WarehouseMappingJob.warehouse_map_id == WarehouseMap.id)
            .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
            .where(WarehouseMappingJob.id == int(job_id), scope)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Warehouse scanned map not found")
    return row[0], row[1], row[2]


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
    dock = (
        await db.execute(
            select(WarehouseDockStation).where(
                WarehouseDockStation.id == int(dock_id),
                WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                WarehouseDockStation.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if dock is None:
        raise HTTPException(status_code=404, detail="Warehouse dock station not found")
    meta = dock.meta_data if isinstance(dock.meta_data, dict) else {}
    return {
        "dock_pose": dock.pose_local_json,
        "entry_pose": dock.entry_pose_local_json,
        "exit_pose": dock.exit_pose_local_json,
        "marker_id": dock.marker_id,
        "dock_yaw_deg": meta.get("dock_yaw_deg"),
        "precision_required": bool(meta.get("precision_required", True)),
    }


async def _build_warehouse_scan_mission_payload(
    db: AsyncSession,
    *,
    user: Any,
    warehouse_map_id: int,
    mission_name: str,
    sensor_rig_id: int | None,
    dock_id: int | None,
    reference_mapping_job_id: int | None,
    cruise_alt: float | None = None,
    work_speed_mps: float | None = None,
) -> tuple[WarehouseMap, MissionCreateIn, float]:
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
    return warehouse_map, mission_payload, base_height_m


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
    _warehouse_map, mission_payload, _base_height_m = await _build_warehouse_scan_mission_payload(
        db,
        user=user,
        warehouse_map_id=warehouse_map_id,
        mission_name=mission_name,
        sensor_rig_id=sensor_rig_id,
        dock_id=dock_id,
        reference_mapping_job_id=reference_mapping_job_id,
        cruise_alt=cruise_alt,
        work_speed_mps=work_speed_mps,
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
    return "UNKNOWN" if required else "DEFERRED"


def _read_odometry_overlay_sync() -> tuple[dict[str, Any], str | None]:
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


async def _read_odometry_overlay() -> tuple[dict[str, Any], str | None]:
    return await asyncio.to_thread(_read_odometry_overlay_sync)


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
    raw = settings.warehouse_ros2_ws.strip()
    return Path(raw or str(_project_root() / "ros2_ws")).resolve()


async def _ensure_ros_bridge_running(*, start: bool) -> tuple[bool | None, str]:
    global _BRIDGE_PROCESS
    ws = _ros2_workspace()
    probe_ok, probe_detail = await asyncio.to_thread(quick_ros_bridge_check, ws)
    if probe_ok is True:
        return True, probe_detail
    if not start:
        return probe_ok, probe_detail

    async with _BRIDGE_LOCK:
        if _BRIDGE_PROCESS is not None and _BRIDGE_PROCESS.poll() is None:
            await asyncio.sleep(0.5)
            probe_ok, probe_detail = await asyncio.to_thread(quick_ros_bridge_check, ws)
            if probe_ok is True:
                return True, probe_detail
            return None, f"Bridge process running; waiting for topics. {probe_detail}"

        setup = ws / "install" / "setup.bash"
        if not setup.exists():
            return False, f"ROS 2 workspace is not built: {setup}"

        log_dir = Path("backend/storage/warehouse_ros/logs").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "warehouse_bridge.log"
        cmd = (
            "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
            f"source {shlex.quote(str(setup))} && "
            "ros2 launch drone_gz_bridge warehouse_bridge.launch.py"
        )
        env = ros_command_env()
        try:
            with log_path.open("ab") as log_file:
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

    grace_s = settings.warehouse_bridge_startup_grace_s
    await asyncio.sleep(max(0.2, min(grace_s, 5.0)))
    probe_ok, probe_detail = await asyncio.to_thread(quick_ros_bridge_check, ws)
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
    should_start_bridge = True
    _ = auto_start_bridge
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

    overlay, overlay_error = await _read_odometry_overlay()
    topic_probe_error: str | None = None
    ros_setup = ws / "install" / "setup.bash"
    if ros_setup.exists():
        try:
            topic_overlay = await asyncio.to_thread(probe_bridge_topics, ws)
            overlay = {**overlay, **topic_overlay}
            if topic_overlay.get("preflight_core_ready") is True:
                overlay_error = None
        except Exception as exc:
            topic_probe_error = f"ROS topic compatibility probe failed: {exc}"
    probe_flags = (
        overlay.get("components")
        if isinstance(overlay.get("components"), dict)
        else overlay
    )
    local_position_ok = probe_flags.get("local_position_ok") is True
    slam_ready = probe_flags.get("slam_ready") is True
    slam_tracking_ok = probe_flags.get("slam_tracking_ok") is True
    tf_ok = probe_flags.get("tf_ok") is True
    nvblox_ok = _bool_from(overlay, "nvblox_ok", "nvblox_healthy", "nvblox_ready")
    sensors_flag = probe_flags.get("sensors_ok")
    sensors_ok = sensors_flag if isinstance(sensors_flag, bool) else None
    rgb_depth_imu_flag = probe_flags.get("rgb_depth_imu_ok")
    rgb_depth_imu_ok = rgb_depth_imu_flag if isinstance(rgb_depth_imu_flag, bool) else None
    lidar_flag = probe_flags.get("lidar_ok")
    lidar_ok = lidar_flag if isinstance(lidar_flag, bool) else None
    source_transport_flag = probe_flags.get("source_transport_ok")
    source_transport_ok = (
        source_transport_flag if isinstance(source_transport_flag, bool) else None
    )
    stable_ms = int(_float_from(overlay, "perception_stable_for_ms", "stable_for_ms") or 0)
    required_stable_ms = int(
        _float_from(overlay, "perception_required_stable_ms", "required_stable_ms") or 8_000
    )
    stability_ok = (
        stable_ms >= required_stable_ms
        and local_position_ok is True
        and (slam_tracking_ok is True or slam_ready is True)
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
    blockers.extend(missing_critical_topic_blockers(overlay))
    if local_position_ok is not True and not any(
        "odometry topic" in blocker.lower() for blocker in blockers
    ):
        blockers.append("Local odometry is not available per warehouse_bridge.yaml.")
    if tf_ok is not True:
        blockers.append("TF tree is missing or stale.")
    if stability_ok is not True:
        blockers.append("Perception stability window has not passed.")
    if overlay_error and overlay_error != "WAREHOUSE_ODOMETRY_STATE_PATH is not configured.":
        blockers.append(overlay_error)
    if topic_probe_error:
        blockers.append(topic_probe_error)

    ros_report = await run_warehouse_ros_preflight_report(
        default_warehouse_scan_preflight_mission_data(),
        cruise_alt=2.0,
    )
    ros_can_start, blockers, ros_failed_checks = apply_ros_preflight_gate(
        categories,
        blockers,
        report=ros_report,
    )
    if categories["odometry"] != "OK":
        local_position_ok = False
    if categories["localization"] == "FAIL":
        slam_ready = False
        slam_tracking_ok = False
    if categories["bridge"] == "FAIL":
        bridge_ok = False
    if categories["tf"] == "FAIL":
        tf_ok = False

    ready_to_fly = (
        ros_can_start
        and not blockers
        and all(categories[key] == "OK" for key in required_keys)
    )
    checks = [{"id": key, "status": value} for key, value in categories.items()]
    topic_diag = {
        "bridge": _topic_diag(
            topic=bridge_url or None,
            status=categories["bridge"],
            detail=bridge_detail,
        ),
        "source_transport": _topic_diag(status=categories["source_transport"]),
        "rgb_depth_imu": _topic_diag(
            topic=str(overlay.get("rgb_topic") or ""),
            status=categories["rgb_depth_imu"],
        ),
        "lidar": _topic_diag(
            topic=str(overlay.get("lidar_topic") or ""),
            status=categories["lidar"],
        ),
        "odometry": _topic_diag(
            topic=str(overlay.get("odometry_topic") or ""),
            status=categories["odometry"],
        ),
        "tf": _topic_diag(status=categories["tf"], detail=None if tf_ok else "TF missing"),
        "nvblox": _topic_diag(
            topic=str(overlay.get("nvblox_topic") or "/nvblox_node/static_esdf_pointcloud"),
            status=categories["nvblox"],
            detail=(
                None
                if nvblox_ok is True
                else (
                    "Nvblox is optional for basic readiness, but required before "
                    "autonomous warehouse mapping flight."
                )
            ),
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
                "ros_domain_id": ros_command_env().get("ROS_DOMAIN_ID"),
                "health_probe_in_progress": False,
            },
            "topics": {
                "by_category": topic_diag,
                "deferred_missing": (
                    []
                    if nvblox_ok is not None
                    else [str(overlay.get("nvblox_topic") or "/nvblox_node/static_esdf_pointcloud")]
                ),
            },
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
            "ros_preflight": {
                "overall_status": str(ros_report.overall_status),
                "can_start": ros_can_start,
                "failed_checks": ros_failed_checks,
                "base_checks": [
                    {"name": r.name, "status": str(r.status), "message": r.message}
                    for r in ros_report.base_checks
                ],
                "mission_checks": [
                    {"name": r.name, "status": str(r.status), "message": r.message}
                    for r in ros_report.mission_checks
                ],
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


@router.get("/maps/{warehouse_map_id}/scan-targets", response_model=list[WarehouseScanTargetRead])
async def list_warehouse_scan_targets(
    warehouse_map_id: int,
    active: bool | None = Query(default=True),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseScanTargetRead]:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    clauses = [WarehouseScanTarget.warehouse_map_id == warehouse_map_id]
    if active is not None:
        clauses.append(WarehouseScanTarget.active.is_(active))
    rows = (
        (
            await db.execute(
                select(WarehouseScanTarget)
                .where(*clauses)
                .order_by(
                    WarehouseScanTarget.priority.asc(),
                    WarehouseScanTarget.aisle_code.asc(),
                    WarehouseScanTarget.rack_code.asc(),
                    WarehouseScanTarget.bin_code.asc(),
                    WarehouseScanTarget.id.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_scan_target_out(row) for row in rows]


@router.post(
    "/maps/{warehouse_map_id}/scan-targets",
    response_model=WarehouseScanTargetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_scan_target(
    warehouse_map_id: int,
    payload: WarehouseScanTargetCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseScanTargetRead:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = WarehouseScanTarget(
        warehouse_map_id=warehouse_map_id,
        reference_model_id=payload.reference_model_id,
        dock_station_id=payload.dock_station_id,
        aisle_code=payload.aisle_code.strip(),
        rack_code=payload.rack_code,
        shelf_level=payload.shelf_level,
        bin_code=payload.bin_code,
        sku=payload.sku,
        barcode=payload.barcode,
        product_name=payload.product_name,
        target_point_local_json=payload.target_point_local_json.model_dump(),
        scan_pose_local_json=payload.scan_pose_local_json.model_dump(),
        shelf_normal_local_json=(
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        ),
        standoff_m=float(payload.standoff_m),
        hover_time_s=float(payload.hover_time_s),
        scan_timeout_s=float(payload.scan_timeout_s),
        priority=int(payload.priority),
        active=bool(payload.active),
    )
    try:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_scan_target_created",
        extra={"warehouse_map_id": warehouse_map_id, "target_id": int(row.id)},
    )
    return _scan_target_out(row)


@router.post(
    "/maps/{warehouse_map_id}/scan-targets/import",
    response_model=list[WarehouseScanTargetRead],
    status_code=status.HTTP_201_CREATED,
)
async def import_warehouse_scan_targets(
    warehouse_map_id: int,
    payload: WarehouseScanTargetImport,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> list[WarehouseScanTargetRead]:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows: list[WarehouseScanTarget] = []
    try:
        for target in payload.targets:
            row = WarehouseScanTarget(
                warehouse_map_id=warehouse_map_id,
                reference_model_id=target.reference_model_id,
                dock_station_id=target.dock_station_id,
                aisle_code=target.aisle_code.strip(),
                rack_code=target.rack_code,
                shelf_level=target.shelf_level,
                bin_code=target.bin_code,
                sku=target.sku,
                barcode=target.barcode,
                product_name=target.product_name,
                target_point_local_json=target.target_point_local_json.model_dump(),
                scan_pose_local_json=target.scan_pose_local_json.model_dump(),
                shelf_normal_local_json=(
                    target.shelf_normal_local_json.model_dump()
                    if target.shelf_normal_local_json is not None
                    else None
                ),
                standoff_m=float(target.standoff_m),
                hover_time_s=float(target.hover_time_s),
                scan_timeout_s=float(target.scan_timeout_s),
                priority=int(target.priority),
                active=bool(target.active),
            )
            db.add(row)
            rows.append(row)
        await db.commit()
        for row in rows:
            await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_scan_targets_imported",
        extra={"warehouse_map_id": warehouse_map_id, "count": len(rows)},
    )
    return [_scan_target_out(row) for row in rows]


@router.get(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    response_model=WarehouseScanTargetRead,
)
async def get_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanTargetRead:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await _get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    return _scan_target_out(row)


@router.patch(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    response_model=WarehouseScanTargetRead,
)
async def update_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    payload: WarehouseScanTargetUpdate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseScanTargetRead:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await _get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    fields_set = getattr(payload, "model_fields_set", set())
    for field_name in (
        "reference_model_id",
        "dock_station_id",
        "rack_code",
        "shelf_level",
        "bin_code",
        "sku",
        "barcode",
        "product_name",
        "standoff_m",
        "hover_time_s",
        "scan_timeout_s",
        "priority",
        "active",
    ):
        if field_name in fields_set:
            setattr(row, field_name, getattr(payload, field_name))
    if "aisle_code" in fields_set and payload.aisle_code is not None:
        row.aisle_code = payload.aisle_code.strip()
    if "target_point_local_json" in fields_set and payload.target_point_local_json is not None:
        row.target_point_local_json = payload.target_point_local_json.model_dump()
    if "scan_pose_local_json" in fields_set and payload.scan_pose_local_json is not None:
        row.scan_pose_local_json = payload.scan_pose_local_json.model_dump()
    if "shelf_normal_local_json" in fields_set:
        row.shelf_normal_local_json = (
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        )
    validated = WarehouseScanTargetCreate.model_validate(
        {
            "reference_model_id": row.reference_model_id,
            "dock_station_id": row.dock_station_id,
            "aisle_code": row.aisle_code,
            "rack_code": row.rack_code,
            "shelf_level": row.shelf_level,
            "bin_code": row.bin_code,
            "sku": row.sku,
            "barcode": row.barcode,
            "product_name": row.product_name,
            "target_point_local_json": row.target_point_local_json,
            "scan_pose_local_json": row.scan_pose_local_json,
            "shelf_normal_local_json": row.shelf_normal_local_json,
            "standoff_m": row.standoff_m,
            "hover_time_s": row.hover_time_s,
            "scan_timeout_s": row.scan_timeout_s,
            "priority": row.priority,
            "active": row.active,
        }
    )
    row.target_point_local_json = validated.target_point_local_json.model_dump()
    row.scan_pose_local_json = validated.scan_pose_local_json.model_dump()
    row.shelf_normal_local_json = (
        validated.shelf_normal_local_json.model_dump()
        if validated.shelf_normal_local_json is not None
        else None
    )
    try:
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    return _scan_target_out(row)


@router.delete(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await _get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    row.active = False
    await db.commit()


@router.post("/scan-targets/compute-scan-pose", response_model=WarehouseScanPoseComputeOut)
async def compute_warehouse_scan_pose(
    payload: WarehouseScanPoseComputeIn,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanPoseComputeOut:
    return WarehouseScanPoseComputeOut(
        scan_pose=compute_scan_pose(
            target_point=payload.target_point,
            shelf_normal=payload.shelf_normal,
            standoff_m=payload.standoff_m,
            yaw_deg=payload.yaw_deg,
        )
    )


@router.post(
    "/inspection-missions",
    response_model=WarehouseInspectionMissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_inspection_mission(
    payload: WarehouseInspectionMissionCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseInspectionMissionRead:
    warehouse_map_id = int(payload.warehouse_map_id)
    await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = (
        (
            await db.execute(
                select(WarehouseScanTarget).where(
                    WarehouseScanTarget.id.in_(payload.target_ids),
                    WarehouseScanTarget.warehouse_map_id == warehouse_map_id,
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {int(row.id): row for row in rows}
    missing = [target_id for target_id in payload.target_ids if int(target_id) not in by_id]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Scan targets not found for selected map: {missing}",
        )
    inactive = [int(row.id) for row in rows if not row.active]
    if inactive:
        raise HTTPException(status_code=400, detail=f"Scan targets are inactive: {inactive}")
    ordered_targets = order_targets(
        [by_id[int(target_id)] for target_id in payload.target_ids],
        optimize_order=payload.optimize_order,
    )
    waypoints = build_inspection_waypoints(
        ordered_targets,
        default_hover_time_s=payload.default_hover_time_s,
        default_scan_timeout_s=payload.default_scan_timeout_s,
    )
    row = WarehouseInspectionMission(
        warehouse_map_id=warehouse_map_id,
        name=payload.name.strip(),
        status="planned",
        scan_mode=payload.scan_mode,
        return_to_dock=bool(payload.return_to_dock),
        target_ids_json=[int(target.id) for target in ordered_targets],
        plan_json={
            "frame_id": "warehouse_map",
            "warehouse_map_to_odom_transform": None,
            "waypoints": [waypoint.model_dump() for waypoint in waypoints],
            "warnings": [
                "ESDF clearance validation not wired in MVP.",
                "warehouse_map == odom assumed until persistent localization is added.",
            ],
        },
    )
    try:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_inspection_mission_planned",
        extra={"mission_id": int(row.id), "target_count": len(ordered_targets)},
    )
    metric_add("warehouse_inspection_missions_planned_total", 1)
    return _inspection_mission_out(row)


@router.get(
    "/inspection-missions/{mission_id}",
    response_model=WarehouseInspectionMissionRead,
)
async def get_warehouse_inspection_mission(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseInspectionMissionRead:
    row = (
        await db.execute(
            select(WarehouseInspectionMission).where(WarehouseInspectionMission.id == mission_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Warehouse inspection mission not found")
    await _get_map_or_404(db, warehouse_map_id=int(row.warehouse_map_id), user=org_user.user)
    return _inspection_mission_out(row)


@router.post(
    "/inspection-missions/{mission_id}/run-mock",
    response_model=list[WarehouseInspectionResultRead],
)
async def run_warehouse_inspection_mission_mock(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> list[WarehouseInspectionResultRead]:
    mission = (
        await db.execute(
            select(WarehouseInspectionMission).where(WarehouseInspectionMission.id == mission_id)
        )
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="Warehouse inspection mission not found")
    await _get_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
    target_ids = [int(value) for value in (mission.target_ids_json or [])]
    targets = (
        (
            await db.execute(
                select(WarehouseScanTarget).where(WarehouseScanTarget.id.in_(target_ids))
            )
        )
        .scalars()
        .all()
    )
    by_id = {int(target.id): target for target in targets}
    ordered = [by_id[target_id] for target_id in target_ids if target_id in by_id]
    scanner = MockWarehouseScanner()
    mission.status = "running"
    results: list[WarehouseInspectionResult] = []
    try:
        for target in ordered:
            logger.info(
                "warehouse_inspection_scan_started",
                extra={"mission_id": int(mission.id), "target_id": int(target.id)},
            )
            scan = await scanner.scan_target(target, timeout_s=float(target.scan_timeout_s))
            result = WarehouseInspectionResult(
                mission_id=int(mission.id),
                target_id=int(target.id),
                status=scan.status,
                expected_barcode=target.barcode,
                detected_barcode=scan.detected_barcode,
                confidence=scan.confidence,
                image_asset_id=scan.image_asset_id,
                video_asset_id=scan.video_asset_id,
                drone_pose_local_json=target.scan_pose_local_json,
                error_message=scan.error_message,
            )
            db.add(result)
            results.append(result)
        mission.status = "completed"
        await db.commit()
        for result in results:
            await db.refresh(result)
    except Exception:
        mission.status = "failed"
        await db.rollback()
        raise
    logger.info(
        "warehouse_inspection_mission_completed",
        extra={"mission_id": int(mission.id), "status": mission.status},
    )
    return [_inspection_result_out(row) for row in results]


@router.get(
    "/inspection-missions/{mission_id}/results",
    response_model=list[WarehouseInspectionResultRead],
)
async def list_warehouse_inspection_results(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseInspectionResultRead]:
    mission = (
        await db.execute(
            select(WarehouseInspectionMission).where(WarehouseInspectionMission.id == mission_id)
        )
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="Warehouse inspection mission not found")
    await _get_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
    rows = (
        (
            await db.execute(
                select(WarehouseInspectionResult)
                .where(WarehouseInspectionResult.mission_id == mission_id)
                .order_by(
                    WarehouseInspectionResult.scanned_at.asc(),
                    WarehouseInspectionResult.id.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_inspection_result_out(row) for row in rows]


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


@router.get(
    "/scanned-maps/{job_id}/live-map-snapshot",
    response_model=WarehouseLiveMapSnapshot,
)
async def get_scanned_map_live_map_snapshot(
    job_id: int,
    mode: Literal["full", "preview"] = "full",
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLiveMapSnapshot:
    client_flight_id = await resolve_client_flight_id_for_scan_job(
        db,
        job_id=job_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if not client_flight_id:
        raise HTTPException(
            status_code=404,
            detail="No live-map flight id found for this scan result.",
        )

    source_filter = (
        {item.strip() for item in source.split(",") if item.strip()}
        if source
        else None
    )
    disk_snapshot = build_disk_live_map_snapshot(
        client_flight_id,
        mode=mode,
        sources=source_filter,
    )
    chunk_counts: dict[str, int] = {}
    point_counts: dict[str, int] = {}
    if disk_snapshot.updates:
        for chunk in disk_snapshot.updates[0].changed_chunks:
            layer = str(chunk.layer or chunk.source or "unknown")
            chunk_counts[layer] = chunk_counts.get(layer, 0) + 1
            if chunk.point_count:
                point_counts[layer] = point_counts.get(layer, 0) + int(
                    chunk.point_count
                )
    if disk_snapshot.manifest is not None:
        point_counts = dict(disk_snapshot.manifest.point_counts or point_counts)
        chunk_counts = dict(disk_snapshot.manifest.chunk_counts or chunk_counts)

    logger.info(
        "scanned_map_replay_snapshot scanned_map_id=%s flight_id=%s source=disk_manifest "
        "chunk_counts=%s point_counts=%s status=%s",
        job_id,
        client_flight_id,
        chunk_counts,
        point_counts,
        disk_snapshot.status,
    )
    return disk_snapshot


@router.get("/scanned-maps/{job_id}/quality", response_model=WarehouseScannedMapQualityOut)
async def get_scanned_map_quality(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapQualityOut:
    job, warehouse_map, model = await _get_scanned_map_row_or_404(
        db, job_id=job_id, user=org_user.user
    )
    assets = await _repo.list_assets_for_models(db, model_ids=[int(model.id)])
    return _quality(job, warehouse_map, assets)


@router.post("/scanned-maps/compare", response_model=WarehouseScannedMapCompareOut)
async def compare_scanned_maps(
    payload: WarehouseScannedMapCompareIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapCompareOut:
    baseline = await _get_scanned_map_row_or_404(
        db, job_id=payload.baseline_job_id, user=org_user.user
    )
    candidate = await _get_scanned_map_row_or_404(
        db, job_id=payload.candidate_job_id, user=org_user.user
    )
    baseline_assets, candidate_assets = await asyncio.gather(
        _repo.list_assets_for_models(db, model_ids=[int(baseline[2].id)]),
        _repo.list_assets_for_models(db, model_ids=[int(candidate[2].id)]),
    )
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
    if drone_connected and snapshot.ready_to_fly and snapshot.nvblox_ok is not True:
        try:
            from backend.modules.warehouse.service.mapping_stack_lifecycle import (
                start_warehouse_mapping_stack,
            )

            await start_warehouse_mapping_stack()
            snapshot = await _build_preflight_snapshot(
                db,
                user=org_user.user,
                deep=effective_deep,
                force=effective_force,
                mission_loaded=mission_loaded,
            )
        except Exception as exc:
            logger.warning("Warehouse preflight could not start nvblox: %s", exc, exc_info=True)
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
    _remember_preflight_run(run)
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
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        get_mapping_stack_status,
    )

    status = await get_mapping_stack_status()
    log_parser = status.nvblox_health.get("log_parser")
    warning = (
        log_parser.get("warning")
        if isinstance(log_parser, dict)
        else None
    )
    return WarehouseMappingStackStatusOut(
        running=status.running,
        pid=status.pid,
        started_at=status.started_at,
        last_exit_code=status.last_exit_code,
        nvblox_running=status.nvblox_running,
        phase=status.phase,
        last_error=status.last_error,
        warning=str(warning) if warning else None,
    )


@router.post("/mapping-stack/start", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_start(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        start_warehouse_mapping_stack,
    )

    status = await start_warehouse_mapping_stack()
    log_parser = status.nvblox_health.get("log_parser")
    warning = (
        log_parser.get("warning")
        if isinstance(log_parser, dict)
        else None
    )
    return WarehouseMappingStackStatusOut(
        running=status.running,
        pid=status.pid,
        started_at=status.started_at,
        last_exit_code=status.last_exit_code,
        nvblox_running=status.nvblox_running,
        phase=status.phase,
        last_error=status.last_error,
        warning=str(warning) if warning else None,
    )


@router.post("/mapping-stack/stop", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_stop(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        get_mapping_stack_status,
        shutdown_warehouse_mapping_stack,
    )

    await shutdown_warehouse_mapping_stack()
    status = await get_mapping_stack_status()
    return WarehouseMappingStackStatusOut(
        running=status.running,
        pid=status.pid,
        started_at=status.started_at,
        last_exit_code=status.last_exit_code,
        nvblox_running=status.nvblox_running,
        phase=status.phase,
        last_error=status.last_error,
    )


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


@router.post("/missions/start", response_model=WarehouseMissionLaunchOut)
async def mission_start(
    payload: WarehouseMissionStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionLaunchOut:
    warehouse_map, mission_payload, base_height_m = await _build_warehouse_scan_mission_payload(
        db,
        user=org_user.user,
        warehouse_map_id=payload.warehouse_map_id,
        mission_name=payload.mission_name,
        sensor_rig_id=payload.sensor_rig_id,
        dock_id=payload.dock_id,
        reference_mapping_job_id=payload.reference_mapping_job_id,
    )
    mission, _ = _build_mission(mission_payload, owner_id=int(org_user.user.id))
    preflight_report = await run_warehouse_ros_preflight_report(
        mission.get_preflight_mission_data(),
        cruise_alt=base_height_m,
    )
    preflight_status = str(preflight_report.overall_status)
    if not warehouse_preflight_can_start(preflight_report):
        failed_checks = warehouse_preflight_failed_checks(preflight_report)
        raise HTTPException(
            status_code=412,
            detail={
                "message": (
                    "Warehouse ROS preflight failed before mission start."
                    + (f" Failed checks: {', '.join(failed_checks)}" if failed_checks else "")
                ),
                "overall_status": preflight_status,
                "blocking_reasons": failed_checks,
                "preflight": {
                    "preflight_run_id": "",
                    "overall_status": preflight_status,
                    "can_start_mission": False,
                },
            },
        )
    launch = await _start_warehouse_scan_mission(
        db=db,
        user=org_user.user,
        warehouse_map_id=payload.warehouse_map_id,
        mission_name=payload.mission_name,
        sensor_rig_id=payload.sensor_rig_id,
        dock_id=payload.dock_id,
        reference_mapping_job_id=payload.reference_mapping_job_id,
    )
    return WarehouseMissionLaunchOut(
        warehouse_map_id=int(warehouse_map.id),
        warehouse_name=warehouse_map.name,
        preflight=WarehouseMissionLaunchPreflightOut(
            preflight_run_id=str(launch.get("preflight_run_id") or ""),
            overall_status=preflight_status,
            can_start_mission=preflight_report.overall_status != CheckStatus.FAIL,
        ),
        mission=MissionCreateOut.model_validate(launch),
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


def _live_map_ingest_authorized(ingest_key: str | None) -> bool:
    expected = str(getattr(settings, "warehouse_live_map_ingest_token", "") or "").strip()
    if not expected:
        logger.warning("Warehouse live-map ingest token is not configured; rejecting ingest request")
        return False
    return bool(ingest_key and hmac.compare_digest(str(ingest_key), expected))


@router.get("/live-map/config")
async def live_map_config(
    _org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    from backend.modules.warehouse.service.live_map_config import live_map_public_config

    return live_map_public_config()


@router.get("/live-map/diagnostics")
async def live_map_diagnostics(
    _org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    from backend.modules.warehouse.service.live_map_diagnostics import (
        run_live_map_diagnostics,
    )

    report = await run_live_map_diagnostics()
    return report.as_dict()


@router.get("/live-map/{flight_id}/snapshot", response_model=WarehouseLiveMapSnapshot)
async def live_map_snapshot(
    flight_id: str,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLiveMapSnapshot:
    started = time.monotonic()
    with observed_span("mapping.replay", flight_id=flight_id, map_id=flight_id):
        snapshot = await warehouse_live_map_stream.snapshot(flight_id)
    metric_record("mapping_replay_latency", (time.monotonic() - started) * 1000.0)
    return snapshot


@router.post("/live-map/{flight_id}/updates", response_model=WarehouseLiveMapPublishOut)
async def publish_live_map_update(
    flight_id: str,
    payload: dict[str, Any],
    x_warehouse_live_map_ingest_key: str | None = Header(
        None, alias="X-Warehouse-Live-Map-Ingest-Key"
    ),
) -> WarehouseLiveMapPublishOut:
    if not _live_map_ingest_authorized(x_warehouse_live_map_ingest_key):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid X-Warehouse-Live-Map-Ingest-Key",
        )
    with observed_span("mapping.live_update.publish", flight_id=flight_id, map_id=flight_id):
        update = normalize_live_map_payload({**payload, "flight_id": flight_id})
        await warehouse_live_map_stream.publish(update)
    metric_add("api_websocket_messages", attrs={"channel": "warehouse_live_map"})
    return WarehouseLiveMapPublishOut(
        accepted=True,
        flight_id=update.flight_id,
        changed_chunk_count=len(update.changed_chunks),
        removed_chunk_count=len(update.removed_chunk_ids),
    )


@router.post(
    "/live-map/{flight_id}/chunks/{chunk_id}",
    response_model=WarehouseLiveMapChunkUploadOut,
)
async def upload_live_map_chunk(
    flight_id: str,
    chunk_id: str,
    kind: Literal["mesh", "point_cloud", "occupancy", "esdf", "costmap"] = Query("mesh"),
    sequence: int = Query(0, ge=0),
    bbox_local_m: list[float] | None = Query(default=None),
    point_count: int | None = Query(default=None, ge=0),
    file: UploadFile = File(...),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLiveMapChunkUploadOut:
    if bbox_local_m is not None and len(bbox_local_m) != 6:
        raise HTTPException(status_code=422, detail="bbox_local_m must contain six values")
    try:
        started = time.monotonic()
        with observed_span(
            "mapping.save_chunk",
            flight_id=flight_id,
            map_id=flight_id,
            chunk_id=chunk_id,
            **{"mapping.layer": kind, "pointcloud.point_count": point_count},
        ):
            stored = await warehouse_live_map_chunk_storage.save_upload(
                flight_id=flight_id,
                chunk_id=chunk_id,
                kind=kind,
                upload=file,
            )
        metric_add("mapping_chunks_saved", attrs={"source": "api_upload", "layer": kind})
        metric_record(
            "mapping_chunk_save_latency",
            (time.monotonic() - started) * 1000.0,
            {"source": "api_upload", "layer": kind},
        )
    except LiveMapStorageError as exc:
        metric_add("mapping_chunk_save_failures", attrs={"source": "api_upload", "layer": kind})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    update = normalize_live_map_payload(
        {
            "flight_id": flight_id,
            "changed_chunks": [
                {
                    "id": stored.chunk_id,
                    "kind": kind,
                    "url": stored.url,
                    "content_type": stored.content_type,
                    "sequence": sequence,
                    "point_count": point_count,
                    "byte_size": stored.byte_size,
                    "checksum_sha256": stored.checksum_sha256,
                    "bbox_local_m": bbox_local_m,
                }
            ],
            "health": {
                "missing_mesh": kind != "mesh",
                "missing_point_cloud": kind != "point_cloud",
                "nvblox_ready": True,
                "mapping_recording": True,
                "stack_running": True,
            },
        }
    )
    await warehouse_live_map_stream.publish(update)
    metric_add("api_websocket_messages", attrs={"channel": "warehouse_live_map"})
    return WarehouseLiveMapChunkUploadOut(
        accepted=True,
        flight_id=flight_id,
        chunk_id=stored.chunk_id,
        url=stored.url,
        byte_size=stored.byte_size,
        checksum_sha256=stored.checksum_sha256,
    )


@router.get("/live-map/{flight_id}/chunks/{chunk_id}/download")
async def live_map_chunk_download(
    flight_id: str,
    chunk_id: str,
    request: Request,
    _org_user: OrgUser = Depends(require_org_user),
):
    with observed_span(
        "mapping.load_chunk",
        flight_id=flight_id,
        map_id=flight_id,
        chunk_id=chunk_id,
    ):
        stored = warehouse_live_map_chunk_storage.resolve(flight_id=flight_id, chunk_id=chunk_id)
    if stored is None:
        logger.warning(
            "live_map_chunk_download flight_id=%s chunk_id=%s exists=false status_code=404",
            flight_id,
            chunk_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Live map chunk {chunk_id!r} for flight {flight_id!r} was not found.",
        )
    etag = f'"{stored.checksum_sha256}"'
    if request.headers.get("if-none-match") == etag:
        logger.debug(
            "live_map_chunk_download flight_id=%s chunk_id=%s exists=true size=%s status_code=304",
            flight_id,
            chunk_id,
            stored.byte_size,
        )
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "ETag": etag,
            },
        )
    logger.info(
        "live_map_chunk_download flight_id=%s chunk_id=%s exists=true size=%s status_code=200",
        flight_id,
        chunk_id,
        stored.byte_size,
    )
    return FileResponse(
        str(stored.path),
        media_type=stored.content_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/live-map/{flight_id}/chunks/batch")
async def live_map_chunk_batch_download(
    flight_id: str,
    payload: WarehouseLiveMapChunkBatchIn,
    _org_user: OrgUser = Depends(require_org_user),
):
    """Stream many chunks in a single response to kill the per-chunk N+1 fan-out.

    Body: {"chunk_ids": [...]} (max WAREHOUSE_LIVE_MAP_BATCH_MAX_CHUNKS).
    Response: a length-prefixed binary stream. For each requested chunk, in order:
        [uint32 big-endian header_len][header_len bytes of UTF-8 JSON][data bytes]
    where the JSON header is
        {"chunk_id", "status", "byte_size", "content_type", "checksum_sha256"}
    and exactly "byte_size" raw data bytes follow when status == 200 (0 when 404).
    The client reads header_len, parses the JSON, then consumes byte_size bytes.
    """
    # De-duplicate while preserving request order.
    seen: set[str] = set()
    requested: list[str] = []
    for raw_id in payload.chunk_ids:
        chunk_id = str(raw_id)
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            requested.append(chunk_id)

    resolved: list[tuple[str, object | None]] = []
    for chunk_id in requested:
        with observed_span(
            "mapping.load_chunk",
            flight_id=flight_id,
            map_id=flight_id,
            chunk_id=chunk_id,
        ):
            stored = warehouse_live_map_chunk_storage.resolve(
                flight_id=flight_id, chunk_id=chunk_id
            )
        resolved.append((chunk_id, stored))

    def _frame_header(meta: dict[str, object]) -> bytes:
        body = json.dumps(meta, separators=(",", ":")).encode("utf-8")
        return len(body).to_bytes(4, "big") + body

    async def _stream():
        for chunk_id, stored in resolved:
            if stored is None:
                yield _frame_header(
                    {
                        "chunk_id": chunk_id,
                        "status": 404,
                        "byte_size": 0,
                        "content_type": "application/octet-stream",
                        "checksum_sha256": "",
                    }
                )
                continue
            yield _frame_header(
                {
                    "chunk_id": chunk_id,
                    "status": 200,
                    "byte_size": int(stored.byte_size),
                    "content_type": stored.content_type,
                    "checksum_sha256": stored.checksum_sha256,
                }
            )
            data = await asyncio.to_thread(stored.path.read_bytes)
            yield data

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.websocket("/live-map/{flight_id}/stream")
async def websocket_live_map_stream(websocket: WebSocket, flight_id: str):
    is_authorized, user_id_or_error = await _authorize_websocket(websocket)
    if not is_authorized:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=user_id_or_error)
        return

    with observed_span("api.websocket.connect", flight_id=flight_id):
        await warehouse_live_map_stream.connect(flight_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping" or '"type":"ping"' in message:
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await warehouse_live_map_stream.disconnect(flight_id, websocket)


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
