from __future__ import annotations

from backend.core.geometry.algorithm_runtime import (
    GEOMETRY_ALGORITHM_VERSION,
    geometry_plan_cache,
    workload_label,
)
from backend.modules.warehouse.planning.local_planner.models import (
    WarehouseDockConfig,
    WarehouseKeepoutZone,
    WarehouseObstacleBox,
    WarehousePlanResult,
)
from backend.modules.warehouse.planning.local_planner.plan_compute import (
    _plan_warehouse_scan_uncached,
)
from backend.modules.warehouse.planning.local_planner.types import (
    WarehouseLaneStrategy,
    WarehouseScanPattern,
    WarehouseViewMode,
)


def plan_warehouse_scan(
    *,
    polygon_local_m: list[tuple[float, float]],
    base_height_m: float,
    corridor_spacing_m: float,
    aisle_axis_deg: float | None,
    clearance_m: float,
    perimeter_offset_m: float,
    scan_pattern: WarehouseScanPattern,
    lane_strategy: WarehouseLaneStrategy,
    view_mode: WarehouseViewMode,
    layer_count: int,
    layer_spacing_m: float,
    ceiling_height_m: float | None,
    ceiling_margin_m: float,
    max_waypoints: int,
    max_route_m: float,
    dock_config: WarehouseDockConfig | None = None,
    allow_inferred_dock: bool = True,
    obstacles_3d: list[WarehouseObstacleBox] | None = None,
    keepout_zones: list[WarehouseKeepoutZone] | None = None,
) -> WarehousePlanResult:
    payload = {
        "polygon_local_m": polygon_local_m,
        "base_height_m": base_height_m,
        "corridor_spacing_m": corridor_spacing_m,
        "aisle_axis_deg": aisle_axis_deg,
        "clearance_m": clearance_m,
        "perimeter_offset_m": perimeter_offset_m,
        "scan_pattern": scan_pattern,
        "lane_strategy": lane_strategy,
        "view_mode": view_mode,
        "layer_count": layer_count,
        "layer_spacing_m": layer_spacing_m,
        "ceiling_height_m": ceiling_height_m,
        "ceiling_margin_m": ceiling_margin_m,
        "max_waypoints": max_waypoints,
        "max_route_m": max_route_m,
        "dock_config": dock_config,
        "allow_inferred_dock": allow_inferred_dock,
        "obstacles_3d": obstacles_3d or [],
        "keepout_zones": keepout_zones or [],
    }
    return geometry_plan_cache.get_or_compute(
        namespace="warehouse_local_plan",
        algorithm_version=GEOMETRY_ALGORITHM_VERSION,
        payload=payload,
        workload=workload_label(
            vertices=len(polygon_local_m),
            obstacles=len(obstacles_3d or []) + len(keepout_zones or []),
        ),
        compute=lambda: _plan_warehouse_scan_uncached(
            polygon_local_m=polygon_local_m,
            base_height_m=base_height_m,
            corridor_spacing_m=corridor_spacing_m,
            aisle_axis_deg=aisle_axis_deg,
            clearance_m=clearance_m,
            perimeter_offset_m=perimeter_offset_m,
            scan_pattern=scan_pattern,
            lane_strategy=lane_strategy,
            view_mode=view_mode,
            layer_count=layer_count,
            layer_spacing_m=layer_spacing_m,
            ceiling_height_m=ceiling_height_m,
            ceiling_margin_m=ceiling_margin_m,
            max_waypoints=max_waypoints,
            max_route_m=max_route_m,
            dock_config=dock_config,
            allow_inferred_dock=allow_inferred_dock,
            obstacles_3d=obstacles_3d,
            keepout_zones=keepout_zones,
        ),
    )
