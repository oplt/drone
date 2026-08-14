from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WarehouseLocalPoint:
    x_m: float
    y_m: float
    z_m: float
    yaw_deg: float | None = None


@dataclass(frozen=True)
class WarehouseDockConfig:
    dock_pose: WarehouseLocalPoint
    entry_pose: WarehouseLocalPoint
    exit_pose: WarehouseLocalPoint
    marker_id: str | None = None
    dock_yaw_deg: float | None = None
    precision_required: bool = True


@dataclass(frozen=True)
class WarehouseScanLayer:
    layer_index: int
    z_m: float
    label: str


@dataclass(frozen=True)
class WarehouseCorridor:
    corridor_id: str
    start: WarehouseLocalPoint
    end: WarehouseLocalPoint
    width_m: float
    heading_deg: float
    axis_deg: float
    source: str = "derived"
    sort_key: float = 0.0


@dataclass(frozen=True)
class WarehouseObstacleBox:
    obstacle_id: str
    center: WarehouseLocalPoint
    size_x_m: float
    size_y_m: float
    size_z_m: float


@dataclass(frozen=True)
class WarehouseKeepoutZone:
    zone_id: str
    footprint: list[tuple[float, float]]
    min_z_m: float | None = None
    max_z_m: float | None = None


@dataclass(frozen=True)
class WarehousePlanSegment:
    """A single flight leg in the local metric frame — no GPS coordinates."""

    segment_id: str
    local_start: WarehouseLocalPoint
    local_end: WarehouseLocalPoint
    work_leg: bool
    leg_type: str
    yaw_deg: float | None = None
    layer_index: int | None = None
    corridor_id: str | None = None
    source: str = "derived"

    @property
    def length_m(self) -> float:
        start = self.local_start
        end = self.local_end
        return math.sqrt(
            (end.x_m - start.x_m) ** 2 + (end.y_m - start.y_m) ** 2 + (end.z_m - start.z_m) ** 2
        )


@dataclass(frozen=True)
class WarehousePlanResult:
    """Plan output — entirely in metres, local drone frame."""

    local_polygon: list[tuple[float, float]]
    flyable_polygon: list[tuple[float, float]]
    dock_point: WarehouseLocalPoint | None
    staging_point: WarehouseLocalPoint | None
    corridors: list[WarehouseCorridor]
    obstacles_3d: list[WarehouseObstacleBox]
    keepout_zones: list[WarehouseKeepoutZone]
    scan_layers: list[WarehouseScanLayer]
    segments: list[WarehousePlanSegment]
    dock_entry_point: WarehouseLocalPoint | None = None
    dock_exit_point: WarehouseLocalPoint | None = None
    dock_yaw_deg: float | None = None
    dock_marker_id: str | None = None
    precision_dock_required: bool = False
    dock_inferred: bool = False
    stats: dict[str, object] = field(default_factory=dict)
