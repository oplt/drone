from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import (
    OrgUser,
    require_mission_exec,
    require_org_user,
    require_org_write,
)
from backend.modules.missions.api import routes as routes_flights
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.warehouse.application import warehouse_application
from backend.modules.warehouse.models import WarehouseAsset, WarehouseMap
from backend.modules.warehouse.planning.exploration import (
    WarehouseExplorationMissionParams,
)
from backend.modules.warehouse.planning.local_planner import (
    WarehouseDockConfig,
    WarehouseLocalPoint,
)
from backend.modules.warehouse.planning.mission import (
    WarehouseDockConfigParams,
    WarehouseDockPoseParams,
    WarehouseMissionDefaults,
    WarehouseMissionDefaultsPatch,
    WarehouseScanMissionParams,
    merge_warehouse_mission_defaults,
)
from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionPort,
    WarehousePerceptionStatus,
    WarehouseReplayStartRequest,
)
from backend.modules.warehouse.service.mapping import WarehouseScanMappingService

router = APIRouter(prefix="/warehouse", tags=["warehouse"])
logger = logging.getLogger(__name__)
_WAREHOUSE_SETTINGS_SECTION = "warehouse"
_WAREHOUSE_MISSION_DEFAULTS_KEY = "mission_defaults"

# ------------------------------------------------------------------ schemas


def get_warehouse_perception_port() -> WarehousePerceptionPort:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    return build_warehouse_perception_port()


class WarehouseScanStartIn(WarehouseMissionDefaultsPatch):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = Field(default="Warehouse Scan", min_length=1, max_length=120)
    reference_mapping_job_id: int | None = Field(default=None, ge=1)
    sensor_rig_id: int | None = Field(default=None, ge=1)
    dock_id: int | None = Field(default=None, ge=1)


class WarehouseExplorationStartIn(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = Field(default="Warehouse Exploration", min_length=1, max_length=120)
    hover_alt_m: float = Field(default=2.5, gt=0.2, le=20.0)
    dock_id: int | None = Field(default=None, ge=1)
    exploration: WarehouseExplorationMissionParams = Field(
        default_factory=WarehouseExplorationMissionParams,
    )


class WarehouseManualMappingStartIn(BaseModel):
    flight_id: str = Field(..., min_length=1, max_length=128)
    warehouse_map_id: int = Field(..., ge=1)
    sensor_rig_id: int | None = Field(default=None, ge=1)
    dock_id: int | None = Field(default=None, ge=1)


class WarehouseManualMappingStopIn(BaseModel):
    flight_id: str = Field(..., min_length=1, max_length=128)
    warehouse_map_id: int | None = Field(default=None, ge=1)


class WarehouseExplorationProfileIn(BaseModel):
    max_radius_m: float = Field(default=80.0, gt=1.0, le=2_000.0)
    min_clearance_m: float = Field(default=1.0, gt=0.1, le=20.0)
    max_frontier_candidates: int = Field(default=8, ge=1, le=100)
    return_battery_reserve_pct: float = Field(default=30.0, ge=5.0, le=95.0)
    max_duration_s: float = Field(default=900.0, gt=10.0, le=86_400.0)


class WarehouseMissionLaunchOut(BaseModel):
    warehouse_map_id: int
    warehouse_name: str
    preflight: routes_flights.PreflightRunOut
    mission: routes_flights.MissionCreateOut


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
    progress: int = 0
    error: str | None = None
    source: str = "real_flight"
    created_at: datetime
    finished_at: datetime | None = None
    polygon_local_m: list[list[float]] = Field(default_factory=list)
    assets: list[WarehouseScannedMapAssetOut] = Field(default_factory=list)


class WarehouseScannedMapQualityOut(BaseModel):
    job_id: int
    quality_score: float | None = None
    coverage_percent: float | None = None
    drift_estimate_m: float | None = None
    source: str = "real_flight"
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


class WarehouseMapCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    # Option A - simple rectangle: supply width and length in metres
    width_m: float | None = Field(default=None, gt=0.0, le=500.0)
    length_m: float | None = Field(default=None, gt=0.0, le=500.0)
    # Option B - explicit polygon in the local metric frame [[x_m, y_m], ...]
    polygon_local_m: list[list[float]] | None = Field(default=None, min_length=3)

    @model_validator(mode="after")
    def _resolve_polygon(self) -> WarehouseMapCreateIn:
        if self.polygon_local_m is not None:
            return self
        if self.width_m is not None and self.length_m is not None:
            width, length = float(self.width_m), float(self.length_m)
            self.polygon_local_m = [
                [0.0, 0.0],
                [width, 0.0],
                [width, length],
                [0.0, length],
            ]
            return self
        raise ValueError("Supply either polygon_local_m, or both width_m and length_m.")


class WarehouseSimulationMapCreateIn(WarehouseMapCreateIn):
    scenario_name: str = Field(default="isaac_sim_warehouse", min_length=1, max_length=128)


class WarehouseSimulationCaptureIn(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    session_dir: str = Field(..., min_length=1, max_length=4096)
    scenario_name: str = Field(default="isaac_sim_warehouse", min_length=1, max_length=128)


class WarehouseSimulationReplayIn(BaseModel):
    replay_id: str = Field(..., min_length=1, max_length=128)
    rosbag_path: str = Field(..., min_length=1, max_length=4096)
    profile: str | None = Field(default=None, max_length=128)


class WarehouseMapOut(BaseModel):
    id: int
    name: str
    area_m2: float | None
    created_at: datetime
    polygon_local_m: list[list[float]] = Field(default_factory=list)


class WarehouseDockLocalPose(BaseModel):
    x_m: float
    y_m: float
    z_m: float
    yaw_deg: float | None = None


class WarehouseDockCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    pose: WarehouseDockLocalPose
    entry_pose: WarehouseDockLocalPose
    exit_pose: WarehouseDockLocalPose
    marker_id: str | None = Field(default=None, max_length=128)
    marker_family: str | None = Field(default="apriltag_36h11", max_length=64)
    marker_size_m: float | None = Field(default=None, gt=0.0, le=5.0)
    marker_pose_covariance: list[float] = Field(default_factory=list, max_length=36)
    charger_type: str | None = Field(default=None, max_length=64)
    precision_required: bool = True


class WarehouseDockUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    pose: WarehouseDockLocalPose | None = None
    entry_pose: WarehouseDockLocalPose | None = None
    exit_pose: WarehouseDockLocalPose | None = None
    marker_id: str | None = Field(default=None, max_length=128)
    marker_family: str | None = Field(default=None, max_length=64)
    marker_size_m: float | None = Field(default=None, gt=0.0, le=5.0)
    marker_pose_covariance: list[float] | None = Field(default=None, max_length=36)
    charger_type: str | None = Field(default=None, max_length=64)
    precision_required: bool | None = None


class WarehouseDockOut(BaseModel):
    id: int
    name: str
    marker_id: str | None
    marker_family: str | None
    marker_size_m: float | None
    marker_pose_covariance: list[float] = Field(default_factory=list)
    marker_visible: bool | None
    last_observed_at: datetime | None
    charger_type: str | None
    pose: WarehouseDockLocalPose
    entry_pose: WarehouseDockLocalPose
    exit_pose: WarehouseDockLocalPose
    active: bool
    created_at: datetime


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
    calibration_status: Literal["missing", "pending", "valid", "expired", "failed"] = "valid"
    calibration_hash: str | None = Field(default=None, max_length=128)
    intrinsics_url: str | None = Field(default=None, max_length=2048)
    extrinsics_url: str | None = Field(default=None, max_length=2048)
    imu_transform_json: dict[str, Any] | None = None
    calibration_meta: dict[str, Any] = Field(default_factory=dict)


class WarehouseSensorRigOut(BaseModel):
    id: int
    name: str
    camera_model: str
    stereo_baseline_m: float | None
    intrinsics_url: str | None
    extrinsics_url: str | None
    imu_transform_json: dict[str, Any]
    firmware_version: str | None
    isaac_ros_version: str | None
    calibration_status: str
    calibration_hash: str | None
    calibration_meta: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime


class WarehouseSensorRigHealthOut(BaseModel):
    sensor_rig: WarehouseSensorRigOut
    perception: WarehousePerceptionStatus
    ready: bool
    blockers: list[str] = Field(default_factory=list)


class WarehousePerceptionHealthOut(WarehousePerceptionStatus):
    pass


# ------------------------------------------------------------------ helpers


def _extract_warehouse_mission_defaults(data: Any) -> WarehouseMissionDefaults:
    if not isinstance(data, dict):
        return WarehouseMissionDefaults()
    warehouse = data.get(_WAREHOUSE_SETTINGS_SECTION)
    if not isinstance(warehouse, dict):
        return WarehouseMissionDefaults()
    raw_defaults = warehouse.get(_WAREHOUSE_MISSION_DEFAULTS_KEY)
    if not isinstance(raw_defaults, dict):
        return WarehouseMissionDefaults()
    try:
        return WarehouseMissionDefaults.model_validate(raw_defaults)
    except ValidationError:
        logger.warning(
            "Invalid stored warehouse mission defaults. Falling back to built-in values."
        )
        return WarehouseMissionDefaults()


async def _get_owned_warehouse_map(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    user,
) -> WarehouseMap:
    warehouse_map = await warehouse_application.get_map(db, map_id=warehouse_map_id, user=user)
    if warehouse_map is None:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    return warehouse_map


def _dock_out(dock) -> WarehouseDockOut:
    def _pose(j: dict) -> WarehouseDockLocalPose:
        return WarehouseDockLocalPose(
            x_m=float(j.get("x_m", 0)),
            y_m=float(j.get("y_m", 0)),
            z_m=float(j.get("z_m", 0)),
            yaw_deg=j.get("yaw_deg"),
        )

    meta = dock.meta_data if isinstance(dock.meta_data, dict) else {}
    last_observed_raw = meta.get("last_observed_at")
    last_observed_at = None
    if isinstance(last_observed_raw, str) and last_observed_raw:
        try:
            last_observed_at = datetime.fromisoformat(last_observed_raw.replace("Z", "+00:00"))
        except ValueError:
            last_observed_at = None
    return WarehouseDockOut(
        id=int(dock.id),
        name=dock.name,
        marker_id=dock.marker_id,
        marker_family=meta.get("marker_family"),
        marker_size_m=meta.get("marker_size_m"),
        marker_pose_covariance=list(meta.get("marker_pose_covariance") or []),
        marker_visible=meta.get("marker_visible"),
        last_observed_at=last_observed_at,
        charger_type=dock.charger_type,
        pose=_pose(dock.pose_local_json),
        entry_pose=_pose(dock.entry_pose_local_json),
        exit_pose=_pose(dock.exit_pose_local_json),
        active=bool(dock.active),
        created_at=dock.created_at,
    )


def _sensor_rig_out(rig) -> WarehouseSensorRigOut:
    return WarehouseSensorRigOut(
        id=int(rig.id),
        name=rig.name,
        camera_model=rig.camera_model,
        stereo_baseline_m=rig.stereo_baseline_m,
        intrinsics_url=rig.intrinsics_url,
        extrinsics_url=rig.extrinsics_url,
        imu_transform_json=dict(rig.imu_transform_json or {}),
        firmware_version=rig.firmware_version,
        isaac_ros_version=rig.isaac_ros_version,
        calibration_status=rig.calibration_status,
        calibration_hash=rig.calibration_hash,
        calibration_meta=dict(rig.calibration_meta or {}),
        active=bool(rig.active),
        created_at=rig.created_at,
        updated_at=rig.updated_at,
    )


def _scanned_map_source(job, warehouse_map) -> str:
    params = job.params if isinstance(job.params, dict) else {}
    map_meta = warehouse_map.meta_data if isinstance(warehouse_map.meta_data, dict) else {}
    source = params.get("input_source") or map_meta.get("source")
    return "simulation" if source in {"simulation", "isaac_sim"} else "real_flight"


def _quality_from_assets(
    *,
    job,
    warehouse_map,
    assets: list[WarehouseAsset],
) -> WarehouseScannedMapQualityOut:
    report: dict[str, Any] = {}
    for asset in assets:
        if asset.type == "QUALITY_REPORT" and isinstance(asset.meta_data, dict):
            report = dict(asset.meta_data)
            capture = report.get("capture_result")
            if isinstance(capture, dict) and isinstance(capture.get("meta"), dict):
                report.update(capture["meta"])
            break
    return WarehouseScannedMapQualityOut(
        job_id=int(job.id),
        quality_score=_float_or_none(report.get("quality_score")),
        coverage_percent=_float_or_none(report.get("coverage_percent")),
        drift_estimate_m=_float_or_none(report.get("drift_estimate_m")),
        source=_scanned_map_source(job, warehouse_map),
        report=report,
    )


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return round(float(candidate) - float(baseline), 4)


def _dock_config_from_station(dock) -> WarehouseDockConfig:
    def _pt(j: dict) -> WarehouseLocalPoint:
        return WarehouseLocalPoint(
            x_m=float(j.get("x_m", 0)),
            y_m=float(j.get("y_m", 0)),
            z_m=float(j.get("z_m", 0)),
            yaw_deg=j.get("yaw_deg"),
        )

    return WarehouseDockConfig(
        dock_pose=_pt(dock.pose_local_json),
        entry_pose=_pt(dock.entry_pose_local_json),
        exit_pose=_pt(dock.exit_pose_local_json),
        marker_id=dock.marker_id,
        dock_yaw_deg=dock.pose_local_json.get("yaw_deg"),
        precision_required=bool(dock.meta_data.get("precision_required", True)),
    )


def _dock_config_params(
    dock_config: WarehouseDockConfig | None,
) -> WarehouseDockConfigParams | None:
    if dock_config is None:
        return None
    return WarehouseDockConfigParams(
        dock_pose=WarehouseDockPoseParams(
            x_m=float(dock_config.dock_pose.x_m),
            y_m=float(dock_config.dock_pose.y_m),
            z_m=float(dock_config.dock_pose.z_m),
            yaw_deg=dock_config.dock_pose.yaw_deg,
        ),
        entry_pose=WarehouseDockPoseParams(
            x_m=float(dock_config.entry_pose.x_m),
            y_m=float(dock_config.entry_pose.y_m),
            z_m=float(dock_config.entry_pose.z_m),
            yaw_deg=dock_config.entry_pose.yaw_deg,
        ),
        exit_pose=WarehouseDockPoseParams(
            x_m=float(dock_config.exit_pose.x_m),
            y_m=float(dock_config.exit_pose.y_m),
            z_m=float(dock_config.exit_pose.z_m),
            yaw_deg=dock_config.exit_pose.yaw_deg,
        ),
        marker_id=dock_config.marker_id,
        dock_yaw_deg=dock_config.dock_yaw_deg,
        precision_required=bool(dock_config.precision_required),
    )


# ------------------------------------------------------------------ mission defaults


@router.get("/perception/health", response_model=WarehousePerceptionHealthOut)
async def get_warehouse_perception_health(
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehousePerceptionHealthOut:
    status = await get_warehouse_perception_port().status()
    if not status.ready:
        components = status.components if isinstance(status.components, dict) else {}
        logger.warning(
            (
                "Warehouse perception health endpoint degraded "
                "status=%s topic_count=%s missing_required=%s"
            ),
            status.status,
            components.get("ros_topic_count"),
            components.get("missing_required_topics"),
            extra={
                "status": status.status,
                "reachable": status.reachable,
                "ros_topic_count": components.get("ros_topic_count"),
                "missing_required_topics": components.get("missing_required_topics"),
                "missing_nvblox_topics": components.get("missing_nvblox_topics"),
                "probe_error": components.get("ros_topic_probe_error"),
            },
        )
    return WarehousePerceptionHealthOut.model_validate(status.model_dump(mode="python"))


# ------------------------------------------------------------------ sensor rigs


@router.get("/sensor-rigs", response_model=list[WarehouseSensorRigOut])
async def list_sensor_rigs(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseSensorRigOut]:
    rigs = await warehouse_application.list_sensor_rigs(
        db, user=org_user.user, limit=limit
    )
    return [_sensor_rig_out(rig) for rig in rigs]


@router.post("/sensor-rigs", response_model=WarehouseSensorRigOut, status_code=201)
async def create_sensor_rig(
    payload: WarehouseSensorRigCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseSensorRigOut:
    try:
        rig = await warehouse_application.create_sensor_rig(
            db, user=org_user.user, payload=payload
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _sensor_rig_out(rig)


@router.post("/sensor-rigs/{sensor_rig_id}/calibration", response_model=WarehouseSensorRigOut)
async def update_sensor_rig_calibration(
    sensor_rig_id: int,
    payload: WarehouseSensorRigCalibrationIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseSensorRigOut:
    rig = await warehouse_application.get_sensor_rig(
        db, sensor_rig_id=sensor_rig_id, user=org_user.user
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Sensor rig not found")
    try:
        updated = await warehouse_application.update_sensor_rig_calibration(
            db, rig=rig, payload=payload
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _sensor_rig_out(updated)


@router.delete("/sensor-rigs/{sensor_rig_id}", status_code=204)
async def delete_sensor_rig(
    sensor_rig_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> None:
    rig = await warehouse_application.get_sensor_rig(
        db, sensor_rig_id=sensor_rig_id, user=org_user.user
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Sensor rig not found")
    await warehouse_application.delete_sensor_rig(db, rig=rig)


@router.get("/sensor-rigs/{sensor_rig_id}/health", response_model=WarehouseSensorRigHealthOut)
async def get_sensor_rig_health(
    sensor_rig_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseSensorRigHealthOut:
    rig = await warehouse_application.get_sensor_rig(
        db, sensor_rig_id=sensor_rig_id, user=org_user.user
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Sensor rig not found")

    perception = await get_warehouse_perception_port().status()
    blockers: list[str] = []
    if rig.calibration_status != "valid":
        blockers.append(f"Calibration status is {rig.calibration_status}.")
    if not rig.intrinsics_url:
        blockers.append("Stereo/camera intrinsics are missing.")
    if not rig.extrinsics_url:
        blockers.append("Camera-to-IMU extrinsics are missing.")
    if not perception.configured:
        blockers.append("Warehouse ROS bridge is not configured.")
    elif not perception.reachable:
        blockers.append("Warehouse ROS bridge is unreachable.")
    elif not perception.ready:
        blockers.append("Warehouse ROS perception stack is not ready.")

    return WarehouseSensorRigHealthOut(
        sensor_rig=_sensor_rig_out(rig),
        perception=perception,
        ready=not blockers,
        blockers=blockers,
    )


@router.get("/mission-defaults", response_model=WarehouseMissionDefaults)
async def get_warehouse_mission_defaults(
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMissionDefaults:
    return _extract_warehouse_mission_defaults(
        await warehouse_application.load_mission_defaults(db)
    )


@router.put("/mission-defaults", response_model=WarehouseMissionDefaults)
async def update_warehouse_mission_defaults(
    payload: WarehouseMissionDefaults,
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionDefaults:
    return await warehouse_application.save_mission_defaults(db, defaults=payload)


@router.get("/exploration-profile", response_model=WarehouseExplorationProfileIn)
async def get_warehouse_exploration_profile(
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseExplorationProfileIn:
    profile = await warehouse_application.load_exploration_profile(db)
    return WarehouseExplorationProfileIn.model_validate(profile or {})


@router.put("/exploration-profile", response_model=WarehouseExplorationProfileIn)
async def update_warehouse_exploration_profile(
    payload: WarehouseExplorationProfileIn,
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseExplorationProfileIn:
    saved = await warehouse_application.save_exploration_profile(
        db,
        profile=payload.model_dump(mode="json"),
    )
    return WarehouseExplorationProfileIn.model_validate(saved)


# ------------------------------------------------------------------ warehouse maps


@router.get("/maps", response_model=list[WarehouseMapOut])
async def list_warehouse_maps(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseMapOut]:
    user = org_user.user
    maps = await warehouse_application.list_maps(db, user=user, limit=limit)
    return [
        WarehouseMapOut(
            id=int(m.id),
            name=m.name,
            area_m2=m.area_m2,
            created_at=m.created_at,
            polygon_local_m=warehouse_application.polygon_from_local(m),
        )
        for m in maps
    ]


@router.post("/maps", response_model=WarehouseMapOut, status_code=201)
async def create_warehouse_map(
    payload: WarehouseMapCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMapOut:
    user = org_user.user
    try:
        polygon_local_m = [tuple(pt) for pt in payload.polygon_local_m]
        warehouse_map = await warehouse_application.create_map(
            db,
            user=user,
            name=payload.name,
            polygon_local_m=polygon_local_m,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WarehouseMapOut(
        id=int(warehouse_map.id),
        name=warehouse_map.name,
        area_m2=warehouse_map.area_m2,
        created_at=warehouse_map.created_at,
        polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
    )


@router.post("/simulation/maps", response_model=WarehouseMapOut, status_code=201)
async def create_simulated_warehouse_map(
    payload: WarehouseSimulationMapCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseMapOut:
    polygon = [(float(x), float(y)) for x, y in (payload.polygon_local_m or [])]
    warehouse_map = await warehouse_application.create_simulation_map(
        db,
        user=org_user.user,
        name=payload.name,
        polygon_local_m=polygon,
        scenario_name=payload.scenario_name,
    )
    return WarehouseMapOut(
        id=int(warehouse_map.id),
        name=warehouse_map.name,
        area_m2=warehouse_map.area_m2,
        created_at=warehouse_map.created_at,
        polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
    )


@router.post("/simulation/captures", status_code=202)
async def create_simulated_capture_job(
    payload: WarehouseSimulationCaptureIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> dict[str, Any]:
    warehouse_map = await _get_owned_warehouse_map(
        db,
        warehouse_map_id=int(payload.warehouse_map_id),
        user=org_user.user,
    )
    polygon = [
        (float(point[0]), float(point[1]))
        for point in warehouse_application.polygon_from_local(warehouse_map)
    ]
    result = await WarehouseScanMappingService().persist_capture(
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        warehouse_map_id=int(warehouse_map.id),
        warehouse_name=warehouse_map.name,
        polygon_local_m=polygon,
        session_dir=Path(payload.session_dir),
        capture_result={
            "absolute_dir": payload.session_dir,
            "meta": {"source": "simulation", "scenario_name": payload.scenario_name},
        },
        source="simulation",
    )
    return result


@router.post("/simulation/replay", status_code=202)
async def start_simulation_replay(
    payload: WarehouseSimulationReplayIn,
    perception: WarehousePerceptionPort = Depends(get_warehouse_perception_port),
    _org_user: OrgUser = Depends(require_mission_exec),
) -> dict[str, Any]:
    result = await perception.start_replay(
        WarehouseReplayStartRequest(
            replay_id=payload.replay_id,
            rosbag_path=payload.rosbag_path,
            profile=payload.profile,
            metadata={"source": "simulation"},
        )
    )
    return result.model_dump(mode="json")


@router.get("/maps/{warehouse_map_id}", response_model=WarehouseMapOut)
async def get_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMapOut:
    warehouse_map = await _get_owned_warehouse_map(
        db, warehouse_map_id=warehouse_map_id, user=org_user.user
    )
    return WarehouseMapOut(
        id=int(warehouse_map.id),
        name=warehouse_map.name,
        area_m2=warehouse_map.area_m2,
        created_at=warehouse_map.created_at,
        polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
    )


@router.delete("/maps/{warehouse_map_id}", status_code=204)
async def delete_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> None:
    user = org_user.user
    deleted = await warehouse_application.delete_map(db, map_id=warehouse_map_id, user=user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse map not found")


# ------------------------------------------------------------------ dock stations


@router.get("/maps/{warehouse_map_id}/docks", response_model=list[WarehouseDockOut])
async def list_dock_stations(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseDockOut]:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    docks = await warehouse_application.list_docks(db, map_id=warehouse_map_id)
    return [_dock_out(d) for d in docks]


@router.post("/maps/{warehouse_map_id}/docks", response_model=WarehouseDockOut, status_code=201)
async def create_dock_station(
    warehouse_map_id: int,
    payload: WarehouseDockCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseDockOut:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    try:
        dock = await warehouse_application.create_dock(db, map_id=warehouse_map_id, payload=payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _dock_out(dock)


@router.delete("/maps/{warehouse_map_id}/docks/{dock_id}", status_code=204)
async def delete_dock_station(
    warehouse_map_id: int,
    dock_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    deactivated = await warehouse_application.delete_dock(
        db, map_id=warehouse_map_id, dock_id=dock_id
    )
    if not deactivated:
        raise HTTPException(status_code=404, detail="Dock station not found")


@router.put("/maps/{warehouse_map_id}/docks/{dock_id}", response_model=WarehouseDockOut)
async def update_dock_station(
    warehouse_map_id: int,
    dock_id: int,
    payload: WarehouseDockUpdateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseDockOut:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    try:
        dock = await warehouse_application.update_dock(
            db,
            map_id=warehouse_map_id,
            dock_id=dock_id,
            payload=payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if dock is None:
        raise HTTPException(status_code=404, detail="Dock station not found")
    return _dock_out(dock)


# ------------------------------------------------------------------ mission


@router.post("/missions/start", response_model=WarehouseMissionLaunchOut)
async def start_warehouse_scan(
    payload: WarehouseScanStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionLaunchOut:
    user = org_user.user
    warehouse_map = await _get_owned_warehouse_map(
        db,
        warehouse_map_id=int(payload.warehouse_map_id),
        user=user,
    )
    mission_defaults = merge_warehouse_mission_defaults(
        _extract_warehouse_mission_defaults(await warehouse_application.load_mission_defaults(db)),
        payload.model_dump(
            exclude={
                "warehouse_map_id",
                "mission_name",
                "reference_mapping_job_id",
                "sensor_rig_id",
                "dock_id",
            },
            exclude_unset=True,
        ),
    )
    polygon_local_m = warehouse_application.polygon_from_local(warehouse_map)

    if payload.sensor_rig_id is None:
        raise HTTPException(status_code=400, detail="Select a calibrated warehouse sensor rig.")
    sensor_rig = await warehouse_application.get_sensor_rig(
        db,
        sensor_rig_id=int(payload.sensor_rig_id),
        user=user,
    )
    if sensor_rig is None:
        raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
    if sensor_rig.calibration_status != "valid":
        raise HTTPException(
            status_code=412,
            detail="Warehouse sensor rig calibration is not valid.",
        )
    if not sensor_rig.intrinsics_url or not sensor_rig.extrinsics_url:
        raise HTTPException(
            status_code=412,
            detail="Warehouse sensor rig calibration files are incomplete.",
        )

    # Use registered dock station if one exists for this map
    dock_config: WarehouseDockConfig | None = None
    docks = await warehouse_application.list_docks(db, map_id=int(warehouse_map.id))
    selected_dock = None
    if payload.dock_id is not None:
        selected_dock = next(
            (dock for dock in docks if int(dock.id) == int(payload.dock_id)),
            None,
        )
        if selected_dock is None:
            raise HTTPException(status_code=404, detail="Dock station not found")
    elif docks:
        selected_dock = docks[0]
    if selected_dock is not None:
        dock_config = _dock_config_from_station(selected_dock)

    mission_payload = routes_flights.MissionCreateIn(
        name=payload.mission_name.strip(),
        # cruise_alt field on MissionCreateIn is used by the orchestrator as the
        # takeoff/hover height; for indoor missions it equals base_height_m (first scan layer).
        cruise_alt=float(mission_defaults.cruise_alt),
        mission_type=MissionType.WAREHOUSE_SCAN,
        warehouse_scan=WarehouseScanMissionParams(
            polygon_local_m=polygon_local_m,
            warehouse_map_id=int(warehouse_map.id),
            warehouse_name=warehouse_map.name,
            reference_mapping_job_id=payload.reference_mapping_job_id,
            sensor_rig_id=int(payload.sensor_rig_id),
            dock_config=_dock_config_params(dock_config),
            corridor_spacing_m=float(mission_defaults.corridor_spacing_m),
            aisle_axis_deg=mission_defaults.aisle_axis_deg,
            clearance_m=float(mission_defaults.clearance_m),
            perimeter_offset_m=float(mission_defaults.perimeter_offset_m),
            scan_pattern=mission_defaults.scan_pattern,
            lane_strategy=mission_defaults.lane_strategy,
            view_mode=mission_defaults.view_mode,
            layer_count=int(mission_defaults.layer_count),
            layer_spacing_m=float(mission_defaults.layer_spacing_m),
            ceiling_height_m=float(mission_defaults.ceiling_height_m),
            ceiling_margin_m=float(mission_defaults.ceiling_margin_m),
            work_speed_mps=float(mission_defaults.work_speed_mps),
            transit_speed_mps=float(mission_defaults.transit_speed_mps),
            scan_pause_s=float(mission_defaults.scan_pause_s),
            interpolate_steps_work_leg=int(mission_defaults.interpolate_steps_work_leg),
            interpolate_steps_transit_leg=int(mission_defaults.interpolate_steps_transit_leg),
        ),
    )

    preflight = await routes_flights.run_preflight(mission_payload, user=user)
    if not preflight.can_start_mission:
        raise HTTPException(
            status_code=412,
            detail={
                "message": (
                    f"Warehouse preflight {preflight.overall_status}. Mission start blocked."
                ),
                "preflight": preflight.model_dump(mode="json"),
            },
        )

    mission_payload.preflight_run_id = preflight.preflight_run_id
    mission = await routes_flights.create_mission(mission_payload, user=user)
    return WarehouseMissionLaunchOut(
        warehouse_map_id=int(warehouse_map.id),
        warehouse_name=warehouse_map.name,
        preflight=preflight,
        mission=mission,
    )


class WarehouseMappingStackStatusOut(BaseModel):
    running: bool
    pid: int | None = None
    started_at: str | None = None
    last_exit_code: int | None = None
    last_error: str | None = None


def _mapping_stack_status_out(status: object) -> WarehouseMappingStackStatusOut:
    from backend.infrastructure.warehouse.mapping_stack_process import MappingStackStatus

    if isinstance(status, MappingStackStatus):
        payload = status.to_dict()
    elif isinstance(status, dict):
        payload = status
    else:
        payload = {}
    return WarehouseMappingStackStatusOut.model_validate(payload)


@router.get("/mapping-stack/status", response_model=WarehouseMappingStackStatusOut)
async def get_warehouse_mapping_stack_status(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        warehouse_mapping_stack_status,
    )

    return _mapping_stack_status_out(await warehouse_mapping_stack_status())


@router.post("/mapping-stack/start", response_model=WarehouseMappingStackStatusOut)
async def start_warehouse_mapping_stack(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        ensure_warehouse_mapping_stack_running,
    )

    return _mapping_stack_status_out(await ensure_warehouse_mapping_stack_running())


@router.post("/mapping-stack/stop", response_model=WarehouseMappingStackStatusOut)
async def stop_warehouse_mapping_stack(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        shutdown_warehouse_mapping_stack,
    )

    return _mapping_stack_status_out(await shutdown_warehouse_mapping_stack())


@router.post("/manual-mapping/start")
async def start_warehouse_manual_mapping(
    payload: WarehouseManualMappingStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
    perception: WarehousePerceptionPort = Depends(get_warehouse_perception_port),
) -> dict[str, Any]:
    user = org_user.user
    warehouse_map = await _get_owned_warehouse_map(
        db,
        warehouse_map_id=int(payload.warehouse_map_id),
        user=user,
    )
    if payload.sensor_rig_id is not None:
        sensor_rig = await warehouse_application.get_sensor_rig(
            db,
            sensor_rig_id=int(payload.sensor_rig_id),
            user=user,
        )
        if sensor_rig is None:
            raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
        if sensor_rig.calibration_status != "valid":
            raise HTTPException(status_code=412, detail="Sensor rig calibration is not valid")
    dock = None
    if payload.dock_id is not None:
        docks = await warehouse_application.list_docks(db, map_id=int(warehouse_map.id))
        dock = next((item for item in docks if int(item.id) == int(payload.dock_id)), None)
        if dock is None:
            raise HTTPException(status_code=404, detail="Dock station not found")
    logger.info(
        (
            "Warehouse manual mapping start requested "
            "flight_id=%s map_id=%s sensor_rig_id=%s dock_id=%s"
        ),
        payload.flight_id,
        int(warehouse_map.id),
        payload.sensor_rig_id,
        payload.dock_id,
        extra={
            "flight_id": payload.flight_id,
            "warehouse_map_id": int(warehouse_map.id),
            "sensor_rig_id": payload.sensor_rig_id,
            "dock_id": payload.dock_id,
            "org_id": org_user.org_id,
            "user_id": user.id,
        },
    )
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        ensure_warehouse_mapping_stack_running,
        mapping_stack_not_running_result,
    )

    stack_status = await ensure_warehouse_mapping_stack_running()
    if not stack_status.running:
        blocked = mapping_stack_not_running_result()
        return blocked.model_dump(mode="json")

    result = await perception.start_mapping(
        WarehouseMappingStartRequest(
            flight_id=payload.flight_id,
            warehouse_map_id=int(warehouse_map.id),
            sensor_rig_id=payload.sensor_rig_id,
            metadata={
                "mission_kind": "warehouse_manual_mapping",
                "warehouse_name": warehouse_map.name,
                "dock_id": int(dock.id) if dock is not None else None,
                "dock_marker_id": dock.marker_id if dock is not None else None,
                "polygon_local_m": warehouse_application.polygon_from_local(warehouse_map),
            },
        )
    )
    logger.info(
        "Warehouse manual mapping start completed flight_id=%s accepted=%s status=%s detail=%s",
        payload.flight_id,
        result.accepted,
        result.status,
        result.detail,
        extra={
            "flight_id": payload.flight_id,
            "accepted": result.accepted,
            "status": result.status,
            "detail": result.detail,
        },
    )
    return result.model_dump(mode="json")


@router.post("/manual-mapping/stop")
async def stop_warehouse_manual_mapping(
    payload: WarehouseManualMappingStopIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
    perception: WarehousePerceptionPort = Depends(get_warehouse_perception_port),
) -> dict[str, Any]:
    logger.info(
        "Warehouse manual mapping stop requested flight_id=%s",
        payload.flight_id,
        extra={"flight_id": payload.flight_id},
    )
    result = await perception.stop_mapping(flight_id=payload.flight_id)
    response = result.model_dump(mode="json")
    logger.info(
        "Warehouse manual mapping stop completed flight_id=%s accepted=%s status=%s detail=%s",
        payload.flight_id,
        result.accepted,
        result.status,
        result.detail,
        extra={
            "flight_id": payload.flight_id,
            "accepted": result.accepted,
            "status": result.status,
            "detail": result.detail,
        },
    )
    from backend.modules.warehouse.service.capture_finalize import (
        persist_warehouse_ros_capture,
        resolve_capture_session_dir,
    )
    from backend.modules.warehouse.service.mapping import WarehouseScanMappingError

    stop_data = result.data if isinstance(result.data, dict) else None
    session_dir = resolve_capture_session_dir(payload.flight_id, stop_data=stop_data)
    session_has_capture = session_dir.exists() and any(session_dir.rglob("*"))
    if not result.accepted and not session_has_capture:
        return response

    warehouse_map_id = payload.warehouse_map_id
    warehouse_name: str | None = None
    polygon_local_m: list[tuple[float, float]] | None = None
    if warehouse_map_id is not None:
        warehouse_map = await _get_owned_warehouse_map(
            db,
            warehouse_map_id=int(warehouse_map_id),
            user=org_user.user,
        )
        warehouse_name = warehouse_map.name
        polygon_local_m = [
            (float(point[0]), float(point[1]))
            for point in warehouse_application.polygon_from_local(warehouse_map)
        ]

    try:
        mapping_job = await persist_warehouse_ros_capture(
            flight_id=payload.flight_id,
            owner_id=int(org_user.user.id),
            org_id=org_user.user.org_id,
            source="warehouse_manual_mapping",
            stop_data=stop_data,
            mission_kind="warehouse_manual_mapping",
            perception=perception,
            warehouse_map_id=warehouse_map_id,
            warehouse_name=warehouse_name,
            polygon_local_m=polygon_local_m,
        )
    except WarehouseScanMappingError as exc:
        logger.warning(
            "Warehouse manual mapping capture persistence failed flight_id=%s error=%s",
            payload.flight_id,
            exc,
            extra={"flight_id": payload.flight_id, "error": str(exc)},
        )
        response["mapping_job"] = {"error": str(exc)}
    else:
        response["mapping_job"] = mapping_job
        logger.info(
            "Warehouse manual mapping capture persisted flight_id=%s job_id=%s",
            payload.flight_id,
            mapping_job.get("job_id"),
            extra={
                "flight_id": payload.flight_id,
                "job_id": mapping_job.get("job_id"),
            },
        )

    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        shutdown_warehouse_mapping_stack,
    )

    stack_status = await shutdown_warehouse_mapping_stack()
    response["mapping_stack"] = stack_status.to_dict()
    return response


@router.post("/missions/exploration/start", response_model=WarehouseMissionLaunchOut)
async def start_warehouse_exploration(
    payload: WarehouseExplorationStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionLaunchOut:
    user = org_user.user
    warehouse_map = await _get_owned_warehouse_map(
        db,
        warehouse_map_id=int(payload.warehouse_map_id),
        user=user,
    )

    docks = await warehouse_application.list_docks(db, map_id=int(warehouse_map.id))
    selected_station = None
    if payload.dock_id is not None:
        for dock in docks:
            if int(dock.id) == int(payload.dock_id):
                selected_station = dock
                break
        if selected_station is None:
            raise HTTPException(status_code=404, detail="Requested dock station not found")
    elif docks:
        selected_station = docks[0]

    dock_config = payload.exploration.dock_config
    if dock_config is None and selected_station is not None:
        dock_config = _dock_config_params(_dock_config_from_station(selected_station))
    if dock_config is None:
        raise HTTPException(
            status_code=412,
            detail=(
                "Indoor warehouse exploration requires a registered dock station "
                "or explicit dock_config."
            ),
        )

    exploration_payload = WarehouseExplorationMissionParams.model_validate(
        {
            **payload.exploration.model_dump(
                mode="python",
                exclude={"warehouse_map_id", "warehouse_name", "dock_config"},
            ),
            "warehouse_map_id": int(warehouse_map.id),
            "warehouse_name": warehouse_map.name,
            "dock_config": dock_config.model_dump(mode="python"),
        }
    )

    mission_payload = routes_flights.MissionCreateIn(
        name=payload.mission_name.strip(),
        cruise_alt=float(payload.hover_alt_m),
        mission_type=MissionType.INDOOR_EXPLORATION,
        warehouse_exploration=exploration_payload,
    )

    preflight = await routes_flights.run_preflight(mission_payload, user=user)
    if not preflight.can_start_mission:
        raise HTTPException(
            status_code=412,
            detail={
                "message": (
                    f"Warehouse exploration preflight {preflight.overall_status}. "
                    "Mission start blocked."
                ),
                "preflight": preflight.model_dump(mode="json"),
            },
        )

    mission_payload.preflight_run_id = preflight.preflight_run_id
    mission = await routes_flights.create_mission(mission_payload, user=user)
    return WarehouseMissionLaunchOut(
        warehouse_map_id=int(warehouse_map.id),
        warehouse_name=warehouse_map.name,
        preflight=preflight,
        mission=mission,
    )


# ------------------------------------------------------------------ scanned maps


@router.get("/scanned-maps", response_model=list[WarehouseScannedMapOut])
async def list_scanned_maps(
    warehouse_map_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseScannedMapOut]:
    user = org_user.user
    rows = await warehouse_application.list_scanned_maps(
        db, user=user, map_id=warehouse_map_id, limit=limit
    )
    if not rows:
        return []

    model_ids = [int(model.id) for _job, _warehouse_map, model in rows]
    asset_rows = await warehouse_application.list_assets(db, model_ids=model_ids)
    assets_by_model: dict[int, list[WarehouseAsset]] = {}
    for asset in asset_rows:
        assets_by_model.setdefault(int(asset.model_id), []).append(asset)

    results: list[WarehouseScannedMapOut] = []
    for job, warehouse_map, model in rows:
        assets = assets_by_model.get(int(model.id), [])
        results.append(
            WarehouseScannedMapOut(
                job_id=int(job.id),
                model_id=int(model.id),
                model_version=int(model.version),
                warehouse_map_id=int(warehouse_map.id),
                warehouse_name=warehouse_map.name,
                status=job.status,
                progress=int(job.progress or 0),
                error=job.error,
                source=_scanned_map_source(job, warehouse_map),
                created_at=job.created_at,
                finished_at=job.finished_at,
                polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
                assets=[
                    WarehouseScannedMapAssetOut(
                        id=int(asset.id),
                        type=asset.type,
                        url=asset.url,
                        created_at=asset.created_at,
                        meta_data=asset.meta_data if isinstance(asset.meta_data, dict) else {},
                    )
                    for asset in assets
                ],
            )
        )
    return results


@router.post("/scanned-maps/compare", response_model=WarehouseScannedMapCompareOut)
async def compare_scanned_maps(
    payload: WarehouseScannedMapCompareIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapCompareOut:
    rows = await warehouse_application.list_scanned_maps(
        db, user=org_user.user, map_id=None, limit=200
    )
    by_job = {int(job.id): (job, warehouse_map, model) for job, warehouse_map, model in rows}
    baseline = by_job.get(int(payload.baseline_job_id))
    candidate = by_job.get(int(payload.candidate_job_id))
    if baseline is None or candidate is None:
        raise HTTPException(status_code=404, detail="Scanned map not found")
    baseline_assets = await warehouse_application.list_assets(db, model_ids=[int(baseline[2].id)])
    candidate_assets = await warehouse_application.list_assets(db, model_ids=[int(candidate[2].id)])
    bq = _quality_from_assets(job=baseline[0], warehouse_map=baseline[1], assets=baseline_assets)
    cq = _quality_from_assets(job=candidate[0], warehouse_map=candidate[1], assets=candidate_assets)
    return WarehouseScannedMapCompareOut(
        baseline_job_id=int(payload.baseline_job_id),
        candidate_job_id=int(payload.candidate_job_id),
        quality_delta=_delta(cq.quality_score, bq.quality_score),
        coverage_delta=_delta(cq.coverage_percent, bq.coverage_percent),
        drift_delta_m=_delta(cq.drift_estimate_m, bq.drift_estimate_m),
    )


@router.get("/scanned-maps/{job_id}/assets", response_model=list[WarehouseScannedMapAssetOut])
async def list_scanned_map_assets(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseScannedMapAssetOut]:
    scanned = await get_scanned_map(job_id=job_id, db=db, org_user=org_user)
    return scanned.assets


@router.get("/scanned-maps/{job_id}/quality", response_model=WarehouseScannedMapQualityOut)
async def get_scanned_map_quality(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapQualityOut:
    rows = await warehouse_application.list_scanned_maps(
        db, user=org_user.user, map_id=None, limit=200
    )
    for job, warehouse_map, model in rows:
        if int(job.id) != int(job_id):
            continue
        assets = await warehouse_application.list_assets(db, model_ids=[int(model.id)])
        return _quality_from_assets(job=job, warehouse_map=warehouse_map, assets=assets)
    raise HTTPException(status_code=404, detail="Scanned map not found")


@router.get("/scanned-maps/{job_id}", response_model=WarehouseScannedMapOut)
async def get_scanned_map(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapOut:
    """Fetch a single scanned map job by its job_id."""
    rows = await warehouse_application.list_scanned_maps(
        db, user=org_user.user, map_id=None, limit=200
    )
    for job, warehouse_map, model in rows:
        if int(job.id) != job_id:
            continue
        asset_rows = await warehouse_application.list_assets(db, model_ids=[int(model.id)])
        return WarehouseScannedMapOut(
            job_id=int(job.id),
            model_id=int(model.id),
            model_version=int(model.version),
            warehouse_map_id=int(warehouse_map.id),
            warehouse_name=warehouse_map.name,
            status=job.status,
            progress=int(job.progress or 0),
            error=job.error,
            source=_scanned_map_source(job, warehouse_map),
            created_at=job.created_at,
            finished_at=job.finished_at,
            polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
            assets=[
                WarehouseScannedMapAssetOut(
                    id=int(a.id),
                    type=a.type,
                    url=a.url,
                    created_at=a.created_at,
                    meta_data=a.meta_data if isinstance(a.meta_data, dict) else {},
                )
                for a in asset_rows
            ],
        )
    raise HTTPException(status_code=404, detail="Scanned map not found")


@router.delete("/scanned-maps/{job_id}", status_code=204)
async def delete_scanned_map(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> None:
    deleted = await warehouse_application.delete_scanned_map(
        db,
        job_id=job_id,
        user=org_user.user,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Scanned map not found")
