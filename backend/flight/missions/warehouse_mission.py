from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, model_validator

from backend.flight.missions.warehouse_local_planner import (
    WarehouseDockConfig,
    WarehouseLaneStrategy,
    WarehouseLocalPoint,
    WarehouseScanPattern,
    WarehouseViewMode,
)
from backend.flight.missions.warehouse_scan import (
    WarehouseScanMission as FlightWarehouseScanMission,
)


class WarehouseMissionDefaults(BaseModel):
    """
    Persistent defaults for indoor warehouse scan missions.
    cruise_alt is kept as the field name for API compatibility but semantically
    means 'base layer height above floor (m)' — NOT an altitude AGL.
    """

    cruise_alt: float = Field(default=4.0, gt=0.0, le=30.0)
    corridor_spacing_m: float = Field(default=2.0, gt=0.1, le=50.0)
    aisle_axis_deg: float | None = Field(default=None, ge=-180.0, le=360.0)
    clearance_m: float = Field(default=0.6, gt=0.1, le=20.0)
    perimeter_offset_m: float = Field(default=0.5, ge=0.0, le=20.0)
    scan_pattern: WarehouseScanPattern = "aisle_serpentine"
    lane_strategy: WarehouseLaneStrategy = "serpentine"
    view_mode: WarehouseViewMode = "forward"
    layer_count: int = Field(default=2, ge=1, le=20)
    layer_spacing_m: float = Field(default=1.2, ge=0.0, le=20.0)
    ceiling_height_m: float = Field(default=8.0, gt=0.1, le=100.0)
    ceiling_margin_m: float = Field(default=0.7, ge=0.0, le=20.0)
    work_speed_mps: float = Field(default=0.8, gt=0.0, le=20.0)
    transit_speed_mps: float = Field(default=1.4, gt=0.0, le=30.0)
    scan_pause_s: float = Field(default=0.0, ge=0.0, le=30.0)
    interpolate_steps_work_leg: int = Field(default=4, ge=0, le=100)
    interpolate_steps_transit_leg: int = Field(default=1, ge=0, le=100)


DEFAULT_WAREHOUSE_MISSION_DEFAULTS = WarehouseMissionDefaults()


class WarehouseMissionDefaultsPatch(BaseModel):
    cruise_alt: float | None = Field(default=None, gt=0.0, le=30.0)
    corridor_spacing_m: float | None = Field(default=None, gt=0.1, le=50.0)
    aisle_axis_deg: float | None = Field(default=None, ge=-180.0, le=360.0)
    clearance_m: float | None = Field(default=None, gt=0.1, le=20.0)
    perimeter_offset_m: float | None = Field(default=None, ge=0.0, le=20.0)
    scan_pattern: WarehouseScanPattern | None = None
    lane_strategy: WarehouseLaneStrategy | None = None
    view_mode: WarehouseViewMode | None = None
    layer_count: int | None = Field(default=None, ge=1, le=20)
    layer_spacing_m: float | None = Field(default=None, ge=0.0, le=20.0)
    ceiling_height_m: float | None = Field(default=None, gt=0.1, le=100.0)
    ceiling_margin_m: float | None = Field(default=None, ge=0.0, le=20.0)
    work_speed_mps: float | None = Field(default=None, gt=0.0, le=20.0)
    transit_speed_mps: float | None = Field(default=None, gt=0.0, le=30.0)
    scan_pause_s: float | None = Field(default=None, ge=0.0, le=30.0)
    interpolate_steps_work_leg: int | None = Field(default=None, ge=0, le=100)
    interpolate_steps_transit_leg: int | None = Field(default=None, ge=0, le=100)


def merge_warehouse_mission_defaults(
    defaults: WarehouseMissionDefaults,
    overrides: WarehouseMissionDefaultsPatch | Mapping[str, Any] | None = None,
) -> WarehouseMissionDefaults:
    if overrides is None:
        return defaults
    update = (
        overrides.model_dump(exclude_unset=True)
        if isinstance(overrides, WarehouseMissionDefaultsPatch)
        else dict(overrides)
    )
    if not update:
        return defaults
    return WarehouseMissionDefaults.model_validate({**defaults.model_dump(mode="python"), **update})


class WarehouseScanMissionParams(BaseModel):
    """
    Parameters for a single indoor warehouse scan mission.
    polygon_local_m defines the warehouse boundary in metres relative to the
    dock/takeoff origin.  No GPS coordinates.
    """

    polygon_local_m: list[list[float]] = Field(
        ...,
        min_length=3,
        description="Warehouse boundary ring as [[x_m, y_m], ...] in the local metric frame",
    )
    warehouse_map_id: int | None = Field(default=None, ge=1)
    warehouse_name: str | None = Field(default=None, min_length=1, max_length=128)
    reference_mapping_job_id: int | None = Field(default=None, ge=1)

    corridor_spacing_m: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.corridor_spacing_m, gt=0.1, le=50.0
    )
    aisle_axis_deg: float | None = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.aisle_axis_deg, ge=-180.0, le=360.0
    )
    clearance_m: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.clearance_m, gt=0.1, le=20.0
    )
    perimeter_offset_m: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.perimeter_offset_m, ge=0.0, le=20.0
    )
    scan_pattern: WarehouseScanPattern = DEFAULT_WAREHOUSE_MISSION_DEFAULTS.scan_pattern
    lane_strategy: WarehouseLaneStrategy = DEFAULT_WAREHOUSE_MISSION_DEFAULTS.lane_strategy
    view_mode: WarehouseViewMode = DEFAULT_WAREHOUSE_MISSION_DEFAULTS.view_mode
    layer_count: int = Field(default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.layer_count, ge=1, le=20)
    layer_spacing_m: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.layer_spacing_m, ge=0.0, le=20.0
    )
    ceiling_height_m: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.ceiling_height_m, gt=0.1, le=100.0
    )
    ceiling_margin_m: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.ceiling_margin_m, ge=0.0, le=20.0
    )
    work_speed_mps: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.work_speed_mps, gt=0.0, le=20.0
    )
    transit_speed_mps: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.transit_speed_mps, gt=0.0, le=30.0
    )
    scan_pause_s: float = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.scan_pause_s, ge=0.0, le=30.0
    )
    interpolate_steps_work_leg: int = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.interpolate_steps_work_leg,
        ge=0,
        le=100,
    )
    interpolate_steps_transit_leg: int = Field(
        default=DEFAULT_WAREHOUSE_MISSION_DEFAULTS.interpolate_steps_transit_leg,
        ge=0,
        le=100,
    )
    dock_config: WarehouseDockConfigParams | None = None

    @model_validator(mode="after")
    def _validate_warehouse_target(self) -> WarehouseScanMissionParams:
        if self.warehouse_map_id is None and not (self.warehouse_name or "").strip():
            raise ValueError(
                "warehouse_scan requires warehouse_map_id or warehouse_name "
                "so the generated map can be stored."
            )
        return self


class WarehouseDockPoseParams(BaseModel):
    x_m: float
    y_m: float
    z_m: float = 0.0
    yaw_deg: float | None = Field(default=None, ge=-180.0, le=360.0)


class WarehouseDockConfigParams(BaseModel):
    dock_pose: WarehouseDockPoseParams
    entry_pose: WarehouseDockPoseParams
    exit_pose: WarehouseDockPoseParams
    marker_id: str | None = Field(default=None, max_length=128)
    dock_yaw_deg: float | None = Field(default=None, ge=-180.0, le=360.0)
    precision_required: bool = True


WarehouseScanMissionParams.model_rebuild()


def _dock_pose_to_local_point(pose: WarehouseDockPoseParams) -> WarehouseLocalPoint:
    return WarehouseLocalPoint(
        x_m=float(pose.x_m),
        y_m=float(pose.y_m),
        z_m=float(pose.z_m),
        yaw_deg=pose.yaw_deg,
    )


def build_warehouse_scan_mission(
    *,
    base_height_m: float,
    scan: WarehouseScanMissionParams,
    owner_id: int | None = None,
):
    poly = [tuple(pt) for pt in scan.polygon_local_m]
    dock_config = None
    if scan.dock_config is not None:
        dock_config = WarehouseDockConfig(
            dock_pose=_dock_pose_to_local_point(scan.dock_config.dock_pose),
            entry_pose=_dock_pose_to_local_point(scan.dock_config.entry_pose),
            exit_pose=_dock_pose_to_local_point(scan.dock_config.exit_pose),
            marker_id=scan.dock_config.marker_id,
            dock_yaw_deg=scan.dock_config.dock_yaw_deg,
            precision_required=bool(scan.dock_config.precision_required),
        )
    mission = FlightWarehouseScanMission(
        base_height_m=float(base_height_m),
        area_polygon_local_m=poly,
        dock_config=dock_config,
        mission_kind="warehouse_scan",
        corridor_spacing_m=float(scan.corridor_spacing_m),
        aisle_axis_deg=scan.aisle_axis_deg,
        clearance_m=float(scan.clearance_m),
        perimeter_offset_m=float(scan.perimeter_offset_m),
        scan_pattern=scan.scan_pattern,
        lane_strategy=scan.lane_strategy,
        view_mode=scan.view_mode,
        layer_count=int(scan.layer_count),
        layer_spacing_m=float(scan.layer_spacing_m),
        ceiling_height_m=float(scan.ceiling_height_m),
        ceiling_margin_m=float(scan.ceiling_margin_m),
        work_speed_mps=float(scan.work_speed_mps),
        transit_speed_mps=float(scan.transit_speed_mps),
        scan_pause_s=float(scan.scan_pause_s),
        interpolate_steps_work_leg=int(scan.interpolate_steps_work_leg),
        interpolate_steps_transit_leg=int(scan.interpolate_steps_transit_leg),
        owner_id=int(owner_id) if owner_id is not None else None,
        warehouse_map_id=int(scan.warehouse_map_id) if scan.warehouse_map_id is not None else None,
        warehouse_name=(scan.warehouse_name or "").strip() or None,
        reference_mapping_job_id=(
            int(scan.reference_mapping_job_id)
            if scan.reference_mapping_job_id is not None
            else None
        ),
    )
    return mission, len(poly)
