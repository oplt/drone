from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.modules.missions.schemas.mission_create import MissionCreateOut

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
