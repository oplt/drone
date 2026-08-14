from __future__ import annotations

from backend.modules.warehouse.planning.local_planner.corridors import (
    _generate_corridors_for_axis,
)
from backend.modules.warehouse.planning.local_planner.geometry import (
    _coerce_xy_ring,
    _dominant_axis_deg,
    _largest_polygon,
    _normalize_angle_deg,
    _normalize_lane_strategy,
    _normalize_scan_pattern,
    _normalize_view_mode,
    _points_close,
    _validate_finite_number,
    _validated_polygon,
)
from backend.modules.warehouse.planning.local_planner.models import (
    WarehouseDockConfig,
    WarehouseKeepoutZone,
    WarehouseLocalPoint,
    WarehouseObstacleBox,
    WarehousePlanResult,
    WarehousePlanSegment,
    WarehouseScanLayer,
)
from backend.modules.warehouse.planning.local_planner.pass_segments import (
    _pass_segments_for_corridor,
)
from backend.modules.warehouse.planning.local_planner.route import (
    _append_segment_route,
    _segment_intersects_keepout,
    _segment_intersects_obstacle,
)
from backend.modules.warehouse.planning.local_planner.segment_geometry import (
    _dock_entry_points,
    _perimeter_segments,
    _segment_from_local_points,
)
from backend.modules.warehouse.planning.local_planner.types import (
    WarehouseLaneStrategy,
    WarehouseScanPattern,
    WarehouseViewMode,
)


def _plan_warehouse_scan_uncached(
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
    """
    Plan a warehouse corridor scan entirely in the local metric frame.
    polygon_local_m is [[x_m, y_m], ...] relative to the dock/takeoff origin.
    No GPS coordinates are used or produced.
    """
    scan_pattern = _normalize_scan_pattern(str(scan_pattern))
    lane_strategy = _normalize_lane_strategy(str(lane_strategy))
    view_mode = _normalize_view_mode(str(view_mode))

    polygon_points = _coerce_xy_ring(polygon_local_m)
    footprint = _validated_polygon(polygon_points)

    base_height_m = _validate_finite_number(base_height_m, name="base_height_m")
    corridor_spacing_m = _validate_finite_number(corridor_spacing_m, name="corridor_spacing_m")
    clearance_m = _validate_finite_number(clearance_m, name="clearance_m")
    perimeter_offset_m = _validate_finite_number(perimeter_offset_m, name="perimeter_offset_m")
    layer_spacing_m = _validate_finite_number(layer_spacing_m, name="layer_spacing_m")
    ceiling_margin_m = _validate_finite_number(ceiling_margin_m, name="ceiling_margin_m")
    max_route_m = _validate_finite_number(max_route_m, name="max_route_m")
    if aisle_axis_deg is not None:
        aisle_axis_deg = _validate_finite_number(aisle_axis_deg, name="aisle_axis_deg")
    if ceiling_height_m is not None:
        ceiling_height_m = _validate_finite_number(ceiling_height_m, name="ceiling_height_m")

    if corridor_spacing_m <= 0:
        raise ValueError("corridor_spacing_m must be positive")
    if clearance_m < 0:
        raise ValueError("clearance_m must be non-negative")
    if max_waypoints < 1:
        raise ValueError("max_waypoints must be at least 1")
    if max_route_m <= 0:
        raise ValueError("max_route_m must be positive")

    inset_m = max(float(perimeter_offset_m), float(clearance_m) * 0.5, 0.0)
    flyable_shape = footprint.buffer(-inset_m) if inset_m > 0 else footprint
    if flyable_shape.is_empty:
        raise ValueError(
            "Warehouse footprint becomes empty after applying clearance and perimeter offset"
        )
    flyable_polygon = _largest_polygon(flyable_shape)
    if flyable_polygon.area <= 0:
        raise ValueError("Warehouse flyable footprint has zero area")

    local_ring = [(float(x), float(y)) for x, y in footprint.exterior.coords[:-1]]
    flyable_ring = [(float(x), float(y)) for x, y in flyable_polygon.exterior.coords[:-1]]

    base_axis = (
        _normalize_angle_deg(float(aisle_axis_deg))
        if aisle_axis_deg is not None
        else _dominant_axis_deg(local_ring)
    )
    corridor_width = max(float(corridor_spacing_m), float(clearance_m) * 2.0, 1.0)

    corridors = _generate_corridors_for_axis(
        flyable_polygon=flyable_polygon,
        axis_deg=base_axis,
        corridor_spacing_m=float(corridor_spacing_m),
        clearance_m=float(clearance_m),
        width_m=corridor_width,
        source="aisle",
    )
    if not corridors:
        raise ValueError("Warehouse planner could not derive any aisle corridors")

    if scan_pattern == "crosshatch":
        corridors.extend(
            _generate_corridors_for_axis(
                flyable_polygon=flyable_polygon,
                axis_deg=base_axis + 90.0,
                corridor_spacing_m=float(corridor_spacing_m),
                clearance_m=float(clearance_m),
                width_m=corridor_width,
                source="cross",
            )
        )

    safe_layer_count = max(1, int(layer_count))
    safe_layer_spacing = max(0.0, float(layer_spacing_m))
    scan_layers = [
        WarehouseScanLayer(
            layer_index=index,
            z_m=float(base_height_m) + (float(index) * safe_layer_spacing),
            label=f"Layer {index + 1}",
        )
        for index in range(safe_layer_count)
    ]
    top_layer_z = max(layer.z_m for layer in scan_layers)
    if ceiling_height_m is not None and top_layer_z + float(ceiling_margin_m) > float(
        ceiling_height_m
    ):
        raise ValueError("Warehouse scan layers exceed the configured ceiling clearance envelope")

    route_segments: list[WarehousePlanSegment] = []
    if scan_pattern == "perimeter_aisle_hybrid":
        for layer in scan_layers:
            _append_segment_route(
                route_segments=route_segments,
                new_segments=_perimeter_segments(
                    flyable_polygon=flyable_polygon,
                    z_m=layer.z_m,
                    layer_index=layer.layer_index,
                ),
            )

    dock_point: WarehouseLocalPoint | None = None
    staging_point: WarehouseLocalPoint | None = None
    dock_entry_point: WarehouseLocalPoint | None = None
    dock_exit_point: WarehouseLocalPoint | None = None
    dock_yaw_deg: float | None = None
    dock_marker_id: str | None = None
    precision_dock_required = False
    dock_inferred = False

    ordered_corridors = sorted(
        corridors,
        key=lambda item: (round(item.sort_key, 6), item.source, item.corridor_id),
    )
    for layer in scan_layers:
        for corridor_index, corridor in enumerate(ordered_corridors):
            reverse = (
                lane_strategy == "serpentine"
                and (corridor_index % 2 == 1)
                and view_mode != "dual_face"
            )
            _append_segment_route(
                route_segments=route_segments,
                new_segments=_pass_segments_for_corridor(
                    corridor=corridor,
                    z_m=layer.z_m,
                    layer_index=layer.layer_index,
                    view_mode=view_mode,
                    reverse=reverse,
                ),
            )

    first_work_segment = next((s for s in route_segments if s.work_leg), None)
    if first_work_segment is not None:
        if dock_config is not None:
            dock_point = dock_config.dock_pose
            dock_entry_point = dock_config.entry_pose
            dock_exit_point = dock_config.exit_pose
            staging_point = dock_entry_point
            dock_yaw_deg = dock_config.dock_yaw_deg
            dock_marker_id = dock_config.marker_id
            precision_dock_required = bool(dock_config.precision_required)
        elif allow_inferred_dock:
            dock_point, staging_point = _dock_entry_points(
                footprint=footprint,
                flyable_polygon=flyable_polygon,
                first_scan_point=first_work_segment.local_start,
                z_m=float(first_work_segment.local_start.z_m),
                corridor_spacing_m=float(corridor_spacing_m),
                clearance_m=float(clearance_m),
            )
            dock_entry_point = staging_point
            dock_exit_point = staging_point
            dock_inferred = True
        else:
            raise ValueError(
                "Warehouse dock pose is required when inferred dock planning is disabled"
            )

        entry_segments: list[WarehousePlanSegment] = []
        if (
            dock_point is not None
            and dock_exit_point is not None
            and not _points_close(dock_point, dock_exit_point)
        ):
            entry_segments.append(
                _segment_from_local_points(
                    segment_id="dock_to_exit",
                    start_point=dock_point,
                    end_point=dock_exit_point,
                    leg_type="dock_depart",
                    work_leg=False,
                    layer_index=first_work_segment.layer_index,
                    corridor_id=first_work_segment.corridor_id,
                    source="dock",
                    yaw_deg=dock_yaw_deg,
                )
            )
        exit_anchor = dock_exit_point or dock_point
        if exit_anchor is not None and not _points_close(
            exit_anchor, first_work_segment.local_start
        ):
            entry_segments.append(
                _segment_from_local_points(
                    segment_id="dock_exit_to_first_aisle",
                    start_point=exit_anchor,
                    end_point=first_work_segment.local_start,
                    leg_type="staging_ingress",
                    work_leg=False,
                    layer_index=first_work_segment.layer_index,
                    corridor_id=first_work_segment.corridor_id,
                    source="dock",
                    yaw_deg=first_work_segment.yaw_deg,
                )
            )
        route_segments = entry_segments + route_segments

        last_segment = route_segments[-1]
        return_segments: list[WarehousePlanSegment] = []
        entry_anchor = dock_entry_point or staging_point or dock_point
        if entry_anchor is not None and not _points_close(last_segment.local_end, entry_anchor):
            return_segments.append(
                _segment_from_local_points(
                    segment_id="last_aisle_to_entry",
                    start_point=last_segment.local_end,
                    end_point=entry_anchor,
                    leg_type="staging_return",
                    work_leg=False,
                    layer_index=last_segment.layer_index,
                    corridor_id=last_segment.corridor_id,
                    source="dock",
                )
            )
        if (
            dock_point is not None
            and entry_anchor is not None
            and not _points_close(entry_anchor, dock_point)
        ):
            return_segments.append(
                _segment_from_local_points(
                    segment_id="entry_to_dock",
                    start_point=entry_anchor,
                    end_point=dock_point,
                    leg_type="dock_return",
                    work_leg=False,
                    layer_index=last_segment.layer_index,
                    corridor_id=last_segment.corridor_id,
                    source="dock",
                    yaw_deg=dock_yaw_deg,
                )
            )
        route_segments.extend(return_segments)

    effective_obstacles = list(obstacles_3d or [])
    effective_keepouts = list(keepout_zones or [])
    for obstacle in effective_obstacles:
        if obstacle.size_x_m <= 0 or obstacle.size_y_m <= 0 or obstacle.size_z_m <= 0:
            raise ValueError(f"Warehouse obstacle '{obstacle.obstacle_id}' must have positive dimensions")
    for zone in effective_keepouts:
        if len(zone.footprint) >= 3:
            _validated_polygon(_coerce_xy_ring(zone.footprint))
    for segment in route_segments:
        for zone in effective_keepouts:
            if _segment_intersects_keepout(segment, zone):
                raise ValueError(f"Warehouse route intersects keepout zone '{zone.zone_id}'")
        for obstacle in effective_obstacles:
            if _segment_intersects_obstacle(segment, obstacle):
                raise ValueError(f"Warehouse route intersects obstacle '{obstacle.obstacle_id}'")

    route_m = sum(segment.length_m for segment in route_segments)
    if len(route_segments) > int(max_waypoints):
        raise ValueError(
            f"Warehouse scan generated {len(route_segments)} segments, exceeding limit {max_waypoints}"
        )
    if route_m > float(max_route_m):
        raise ValueError(
            f"Warehouse scan route is {route_m:.1f}m, exceeding limit {max_route_m:.1f}m"
        )

    stats: dict[str, object] = {
        "aisle_axis_deg": round(base_axis, 2),
        "corridors": len(corridors),
        "layers": len(scan_layers),
        "segments": len(route_segments),
        "route_m": round(route_m, 2),
        "scan_pattern": scan_pattern,
        "view_mode": view_mode,
        "ceiling_height_m": ceiling_height_m,
        "ceiling_margin_m": float(ceiling_margin_m),
        "dock_planned": dock_point is not None,
        "dock_inferred": dock_inferred,
        "precision_dock_required": precision_dock_required,
        "dock_marker_id": dock_marker_id,
        "obstacle_count": len(effective_obstacles),
        "keepout_count": len(effective_keepouts),
        "limits": {
            "max_waypoints": int(max_waypoints),
            "max_route_m": float(max_route_m),
            "backtracking_limit": 0,
        },
    }
    return WarehousePlanResult(
        local_polygon=local_ring,
        flyable_polygon=flyable_ring,
        dock_point=dock_point,
        staging_point=staging_point,
        corridors=corridors,
        obstacles_3d=effective_obstacles,
        keepout_zones=effective_keepouts,
        scan_layers=scan_layers,
        segments=route_segments,
        dock_entry_point=dock_entry_point,
        dock_exit_point=dock_exit_point,
        dock_yaw_deg=dock_yaw_deg,
        dock_marker_id=dock_marker_id,
        precision_dock_required=precision_dock_required,
        dock_inferred=dock_inferred,
        stats=stats,
    )
