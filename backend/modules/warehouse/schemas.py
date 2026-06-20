from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WAREHOUSE_MAP_FRAME_ID = "warehouse_map"


def _finite(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    return value


def _strip_required(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be blank")
    return text


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class WarehouseLocalPoint(BaseModel):
    frame_id: str = Field(default=WAREHOUSE_MAP_FRAME_ID, min_length=1, max_length=64)
    x_m: float
    y_m: float
    z_m: float

    @field_validator("frame_id")
    @classmethod
    def _clean_frame_id(cls, value: str) -> str:
        return _strip_required(value, "frame_id")

    @field_validator("x_m", "y_m", "z_m")
    @classmethod
    def _finite_coordinate(cls, value: float, info) -> float:
        return _finite(value, str(info.field_name))


class WarehouseLocalPose(WarehouseLocalPoint):
    yaw_deg: float | None = Field(default=None, ge=-180.0, le=180.0)

    @field_validator("yaw_deg")
    @classmethod
    def _finite_yaw(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _finite(value, "yaw_deg")


class WarehouseShelfNormal(BaseModel):
    frame_id: str = Field(default=WAREHOUSE_MAP_FRAME_ID, min_length=1, max_length=64)
    x: float
    y: float
    z: float = 0.0

    @field_validator("frame_id")
    @classmethod
    def _clean_frame_id(cls, value: str) -> str:
        return _strip_required(value, "frame_id")

    @field_validator("x", "y", "z")
    @classmethod
    def _finite_coordinate(cls, value: float, info) -> float:
        return _finite(value, str(info.field_name))

    @model_validator(mode="after")
    def _non_zero(self) -> WarehouseShelfNormal:
        if math.sqrt(self.x**2 + self.y**2 + self.z**2) <= 1e-9:
            raise ValueError("shelf normal vector must be non-zero")
        return self


class WarehouseScanTargetBase(BaseModel):
    reference_model_id: int | None = Field(default=None, ge=1)
    dock_station_id: int | None = Field(default=None, ge=1)
    aisle_code: str = Field(..., min_length=1, max_length=64)
    rack_code: str | None = Field(default=None, max_length=64)
    shelf_level: int | None = Field(default=None, ge=0)
    bin_code: str | None = Field(default=None, max_length=64)
    sku: str | None = Field(default=None, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    product_name: str | None = Field(default=None, max_length=255)
    target_point_local_json: WarehouseLocalPoint
    scan_pose_local_json: WarehouseLocalPose
    shelf_normal_local_json: WarehouseShelfNormal | None = None
    standoff_m: float = Field(default=1.2, gt=0.0, le=20.0)
    hover_time_s: float = Field(default=3.0, ge=0.0, le=300.0)
    scan_timeout_s: float = Field(default=8.0, gt=0.0, le=300.0)
    priority: int = Field(default=100, ge=0)
    active: bool = True

    @field_validator("aisle_code")
    @classmethod
    def _clean_required_text(cls, value: str, info) -> str:
        return _strip_required(value, str(info.field_name))

    @field_validator("rack_code", "bin_code", "sku", "barcode", "product_name")
    @classmethod
    def _clean_optional_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @field_validator("standoff_m", "hover_time_s", "scan_timeout_s")
    @classmethod
    def _finite_times(cls, value: float, info) -> float:
        return _finite(value, str(info.field_name))

    @model_validator(mode="after")
    def _matching_frames(self) -> WarehouseScanTargetBase:
        if self.target_point_local_json.frame_id != self.scan_pose_local_json.frame_id:
            raise ValueError("target point and scan pose frame_id must match")
        if (
            self.shelf_normal_local_json is not None
            and self.shelf_normal_local_json.frame_id != self.target_point_local_json.frame_id
        ):
            raise ValueError("shelf normal frame_id must match target point frame_id")
        return self


class WarehouseScanTargetCreate(WarehouseScanTargetBase):
    pass


class WarehouseScanTargetUpdate(BaseModel):
    reference_model_id: int | None = Field(default=None, ge=1)
    dock_station_id: int | None = Field(default=None, ge=1)
    aisle_code: str | None = Field(default=None, min_length=1, max_length=64)
    rack_code: str | None = Field(default=None, max_length=64)
    shelf_level: int | None = Field(default=None, ge=0)
    bin_code: str | None = Field(default=None, max_length=64)
    sku: str | None = Field(default=None, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    product_name: str | None = Field(default=None, max_length=255)
    target_point_local_json: WarehouseLocalPoint | None = None
    scan_pose_local_json: WarehouseLocalPose | None = None
    shelf_normal_local_json: WarehouseShelfNormal | None = None
    standoff_m: float | None = Field(default=None, gt=0.0, le=20.0)
    hover_time_s: float | None = Field(default=None, ge=0.0, le=300.0)
    scan_timeout_s: float | None = Field(default=None, gt=0.0, le=300.0)
    priority: int | None = Field(default=None, ge=0)
    active: bool | None = None

    @field_validator("aisle_code")
    @classmethod
    def _clean_required_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _strip_required(value, str(info.field_name))

    @field_validator("rack_code", "bin_code", "sku", "barcode", "product_name")
    @classmethod
    def _clean_optional_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @field_validator("standoff_m", "hover_time_s", "scan_timeout_s")
    @classmethod
    def _finite_times(cls, value: float | None, info) -> float | None:
        if value is None:
            return None
        return _finite(value, str(info.field_name))


class WarehouseScanTargetRead(WarehouseScanTargetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_map_id: int
    created_at: datetime
    updated_at: datetime


class WarehouseScanTargetPage(BaseModel):
    items: list[WarehouseScanTargetRead]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class WarehouseScanTargetImport(BaseModel):
    targets: list[WarehouseScanTargetCreate] = Field(..., min_length=1, max_length=1000)


WarehouseInspectionScanMode = Literal["barcode", "product_photo", "visual_check", "mixed"]
WarehouseInspectionMissionStatus = Literal["planned", "running", "completed", "failed", "aborted"]
WarehouseInspectionResultStatus = Literal["success", "failed", "skipped", "timeout", "mismatch"]


class WarehouseInspectionMissionCreate(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    name: str = Field(default="Warehouse Product Scan", min_length=1, max_length=160)
    target_ids: list[int] = Field(..., min_length=1)
    scan_mode: WarehouseInspectionScanMode = "barcode"
    optimize_order: bool = True
    return_to_dock: bool = True
    default_hover_time_s: float | None = Field(default=None, ge=0.0, le=300.0)
    default_scan_timeout_s: float | None = Field(default=None, gt=0.0, le=300.0)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return _strip_required(value, "name")

    @field_validator("target_ids")
    @classmethod
    def _dedupe_target_ids(cls, value: list[int]) -> list[int]:
        seen: set[int] = set()
        deduped: list[int] = []
        for item in value:
            target_id = int(item)
            if target_id <= 0:
                raise ValueError("target_ids must contain positive ids")
            if target_id not in seen:
                seen.add(target_id)
                deduped.append(target_id)
        if not deduped:
            raise ValueError("target_ids must contain at least one id")
        return deduped

    @field_validator("default_hover_time_s", "default_scan_timeout_s")
    @classmethod
    def _finite_times(cls, value: float | None, info) -> float | None:
        if value is None:
            return None
        return _finite(value, str(info.field_name))


class WarehouseInspectionWaypoint(BaseModel):
    target_id: int
    purpose: str
    pose: WarehouseLocalPose
    hover_time_s: float
    scan_timeout_s: float
    metadata: dict[str, object] = Field(default_factory=dict)


class WarehouseInspectionMissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_map_id: int
    name: str
    status: WarehouseInspectionMissionStatus | str
    scan_mode: WarehouseInspectionScanMode | str
    return_to_dock: bool
    target_ids: list[int]
    waypoints: list[WarehouseInspectionWaypoint]
    created_at: datetime
    updated_at: datetime


class WarehouseInspectionResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mission_id: int
    target_id: int
    status: WarehouseInspectionResultStatus | str
    expected_barcode: str | None = None
    detected_barcode: str | None = None
    confidence: float | None = None
    image_asset_id: int | None = None
    video_asset_id: int | None = None
    drone_pose_local_json: WarehouseLocalPose | None = None
    error_message: str | None = None
    scanned_at: datetime


class WarehouseInspectionResultPage(BaseModel):
    items: list[WarehouseInspectionResultRead]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class WarehouseScanPoseComputeIn(BaseModel):
    target_point: WarehouseLocalPoint
    shelf_normal: WarehouseShelfNormal | None = None
    standoff_m: float = Field(default=1.2, gt=0.0, le=20.0)
    yaw_deg: float | None = Field(default=None, ge=-180.0, le=180.0)


class WarehouseScanPoseComputeOut(BaseModel):
    scan_pose: WarehouseLocalPose


class WarehouseStructureExtractIn(BaseModel):
    """Optional overrides for an automatic structure-extraction run."""

    voxel_m: float | None = Field(default=None, gt=0.0, le=1.0)
    grid_res_m: float | None = Field(default=None, gt=0.0, le=2.0)
    bin_pitch_m: float | None = Field(default=None, gt=0.0, le=10.0)
    standoff_m: float | None = Field(default=None, gt=0.0, le=20.0)
    drone_radius_m: float | None = Field(default=None, gt=0.0, le=5.0)
    clearance_margin_m: float | None = Field(default=None, ge=0.0, le=5.0)
    min_aisle_width_m: float | None = Field(default=None, gt=0.0, le=20.0)
    shelf_min_spacing_m: float | None = Field(default=None, gt=0.0, le=10.0)
    max_shelf_levels: int | None = Field(default=None, ge=1, le=12)
    max_bins_per_rack_face: int | None = Field(default=None, ge=1, le=80)
    axis_deg: float | None = Field(default=None, ge=-180.0, le=180.0)

    def to_params_payload(self) -> dict[str, float]:
        payload: dict[str, float] = {}
        for name in (
            "voxel_m",
            "grid_res_m",
            "bin_pitch_m",
            "standoff_m",
            "drone_radius_m",
            "clearance_margin_m",
            "min_aisle_width_m",
            "shelf_min_spacing_m",
            "max_shelf_levels",
            "max_bins_per_rack_face",
            "axis_deg",
        ):
            value = getattr(self, name)
            if value is not None:
                payload[name] = float(value)
        return payload


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


class WarehouseStructureExtractOut(BaseModel):
    status: Literal["queued"]
    warehouse_map_id: int
    model_id: int
    client_flight_id: str
    task_id: str | None = None


class WarehouseStructureSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    status: Literal["not_started", "queued", "running", "ready", "needs_review", "failed"] = "ready"
    warehouse_map_id: int
    model_id: int | None = None
    client_flight_id: str | None = None
    task_id: str | None = None
    error_message: str | None = None
    generated_at: str | None = None
    target_count: int = 0
    active_target_count: int = 0
    quality_status: Literal["ready", "needs_review", "failed"] | None = None
    quality_reasons: list[str] = Field(default_factory=list)
    confidence: float | None = None
    summary: dict[str, object] = Field(default_factory=dict)
