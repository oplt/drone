from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional, Sequence

from shapely.affinity import rotate as rotate_geometry
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points

WarehouseScanPattern = Literal[
    "aisle_serpentine",
    "stacked_passes",
    "crosshatch",
    "perimeter_aisle_hybrid",
]
WarehouseLaneStrategy = Literal["serpentine", "one_way"]
WarehouseViewMode = Literal["forward", "left_face", "right_face", "dual_face"]


# ---------------------------------------------------------------------------
# Pure-metric helpers (no lon/lat anywhere)
# ---------------------------------------------------------------------------

def _distance_2d(a: "WarehouseLocalPoint", b: "WarehouseLocalPoint") -> float:
    return math.hypot(b.x_m - a.x_m, b.y_m - a.y_m)


def _distance_3d(a: "WarehouseLocalPoint", b: "WarehouseLocalPoint") -> float:
    return math.sqrt(
        (b.x_m - a.x_m) ** 2
        + (b.y_m - a.y_m) ** 2
        + (b.z_m - a.z_m) ** 2
    )


def _points_close(
        a: "WarehouseLocalPoint",
        b: "WarehouseLocalPoint",
        tol_m: float = 1e-3,
) -> bool:
    return _distance_3d(a, b) <= tol_m


def _heading_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _normalize_angle_deg(value: float) -> float:
    normalized = value % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _dominant_axis_deg(polygon_xy: Sequence[tuple[float, float]]) -> float:
    pts = list(polygon_xy)
    if len(pts) >= 2 and pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    longest_edge: tuple[tuple[float, float], tuple[float, float]] | None = None
    longest_len = -1.0
    for a, b in zip(pts, pts[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length > longest_len:
            longest_len = length
            longest_edge = (a, b)
    if longest_edge is None:
        return 0.0
    return _normalize_angle_deg(_heading_deg(longest_edge[0], longest_edge[1]))


def _largest_polygon(geometry: Polygon) -> Polygon:
    if geometry.geom_type == "Polygon":
        return geometry
    if geometry.geom_type == "MultiPolygon":
        return max(geometry.geoms, key=lambda poly: poly.area)
    raise ValueError("Warehouse scan polygon produced an unsupported geometry")


def _collect_lines(geometry: object) -> list[LineString]:
    if geometry is None:
        return []
    geom_type = getattr(geometry, "geom_type", None)
    if geom_type == "LineString":
        return [geometry]  # type: ignore[list-item]
    if geom_type == "MultiLineString":
        return list(geometry.geoms)  # type: ignore[return-value]
    if geom_type == "GeometryCollection":
        lines: list[LineString] = []
        for item in geometry.geoms:  # type: ignore[attr-defined]
            lines.extend(_collect_lines(item))
        return lines
    return []


# ---------------------------------------------------------------------------
# Data structures — all coordinates in metres, local drone frame
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WarehouseLocalPoint:
    x_m: float
    y_m: float
    z_m: float
    yaw_deg: Optional[float] = None


@dataclass(frozen=True)
class WarehouseDockConfig:
    dock_pose: WarehouseLocalPoint
    entry_pose: WarehouseLocalPoint
    exit_pose: WarehouseLocalPoint
    marker_id: Optional[str] = None
    dock_yaw_deg: Optional[float] = None
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
    min_z_m: Optional[float] = None
    max_z_m: Optional[float] = None


@dataclass(frozen=True)
class WarehousePlanSegment:
    """A single flight leg in the local metric frame — no GPS coordinates."""
    segment_id: str
    local_start: WarehouseLocalPoint
    local_end: WarehouseLocalPoint
    work_leg: bool
    leg_type: str
    yaw_deg: Optional[float] = None
    layer_index: Optional[int] = None
    corridor_id: Optional[str] = None
    source: str = "derived"

    @property
    def length_m(self) -> float:
        return _distance_3d(self.local_start, self.local_end)


@dataclass(frozen=True)
class WarehousePlanResult:
    """Plan output — entirely in metres, local drone frame."""
    local_polygon: list[tuple[float, float]]
    flyable_polygon: list[tuple[float, float]]
    dock_point: Optional[WarehouseLocalPoint]
    staging_point: Optional[WarehouseLocalPoint]
    corridors: list[WarehouseCorridor]
    obstacles_3d: list[WarehouseObstacleBox]
    keepout_zones: list[WarehouseKeepoutZone]
    scan_layers: list[WarehouseScanLayer]
    segments: list[WarehousePlanSegment]
    dock_entry_point: Optional[WarehouseLocalPoint] = None
    dock_exit_point: Optional[WarehouseLocalPoint] = None
    dock_yaw_deg: Optional[float] = None
    dock_marker_id: Optional[str] = None
    precision_dock_required: bool = False
    dock_inferred: bool = False
    stats: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers — geometry only
# ---------------------------------------------------------------------------

def _clip_segment_endpoints(
        start_xy: tuple[float, float],
        end_xy: tuple[float, float],
        trim_m: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    segment_len = math.hypot(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])
    if segment_len <= 0:
        return None
    if trim_m <= 0:
        return start_xy, end_xy
    if segment_len <= trim_m * 2.0:
        return None
    ux = (end_xy[0] - start_xy[0]) / segment_len
    uy = (end_xy[1] - start_xy[1]) / segment_len
    return (
        (start_xy[0] + ux * trim_m, start_xy[1] + uy * trim_m),
        (end_xy[0] - ux * trim_m, end_xy[1] - uy * trim_m),
    )


def _nearest_boundary_point(
        polygon: Polygon,
        target_xy: tuple[float, float],
) -> tuple[float, float]:
    boundary = polygon.exterior
    nearest = nearest_points(boundary, Point(target_xy))[0]
    return float(nearest.x), float(nearest.y)


def _point_towards(
        start_xy: tuple[float, float],
        target_xy: tuple[float, float],
        distance_m: float,
) -> tuple[float, float]:
    dx = float(target_xy[0]) - float(start_xy[0])
    dy = float(target_xy[1]) - float(start_xy[1])
    total = math.hypot(dx, dy)
    if total <= 1e-6:
        return start_xy
    scale = min(1.0, max(0.0, float(distance_m)) / total)
    return (
        float(start_xy[0]) + dx * scale,
        float(start_xy[1]) + dy * scale,
    )


def _dock_entry_points(
        *,
        footprint: Polygon,
        flyable_polygon: Polygon,
        first_scan_point: WarehouseLocalPoint,
        z_m: float,
        corridor_spacing_m: float,
        clearance_m: float,
) -> tuple[WarehouseLocalPoint, WarehouseLocalPoint]:
    target_xy = (float(first_scan_point.x_m), float(first_scan_point.y_m))
    dock_xy = _nearest_boundary_point(footprint, target_xy)
    flyable_edge_xy = _nearest_boundary_point(flyable_polygon, target_xy)
    staging_step_m = max(float(clearance_m) * 1.5, float(corridor_spacing_m) * 0.5, 0.75)
    staging_xy = _point_towards(flyable_edge_xy, target_xy, staging_step_m)
    dock_point = WarehouseLocalPoint(x_m=dock_xy[0], y_m=dock_xy[1], z_m=float(z_m))
    staging_point = WarehouseLocalPoint(
        x_m=float(staging_xy[0]),
        y_m=float(staging_xy[1]),
        z_m=float(z_m),
    )
    return dock_point, staging_point


def _segment_from_local_points(
        *,
        segment_id: str,
        start_point: WarehouseLocalPoint,
        end_point: WarehouseLocalPoint,
        leg_type: str,
        work_leg: bool,
        layer_index: Optional[int],
        corridor_id: Optional[str],
        source: str,
        yaw_deg: Optional[float] = None,
) -> WarehousePlanSegment:
    return WarehousePlanSegment(
        segment_id=segment_id,
        local_start=start_point,
        local_end=end_point,
        work_leg=work_leg,
        leg_type=leg_type,
        yaw_deg=yaw_deg,
        layer_index=layer_index,
        corridor_id=corridor_id,
        source=source,
    )


def _perimeter_segments(
        *,
        flyable_polygon: Polygon,
        z_m: float,
        layer_index: int,
) -> list[WarehousePlanSegment]:
    ring = list(flyable_polygon.exterior.coords)
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return []

    points = [
        WarehouseLocalPoint(x_m=float(x), y_m=float(y), z_m=float(z_m))
        for x, y in ring
    ]
    segments: list[WarehousePlanSegment] = []
    for idx, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        yaw = _normalize_angle_deg(_heading_deg((a.x_m, a.y_m), (b.x_m, b.y_m)))
        segments.append(
            WarehousePlanSegment(
                segment_id=f"perimeter_{layer_index}_{idx}",
                local_start=a,
                local_end=b,
                work_leg=True,
                leg_type="perimeter",
                yaw_deg=yaw,
                layer_index=layer_index,
                corridor_id=f"perimeter_{layer_index}",
                source="perimeter",
            )
        )
    return segments


def _generate_corridors_for_axis(
        *,
        flyable_polygon: Polygon,
        axis_deg: float,
        corridor_spacing_m: float,
        clearance_m: float,
        width_m: float,
        source: str,
) -> list[WarehouseCorridor]:
    rotated = rotate_geometry(flyable_polygon, -axis_deg, origin=(0, 0))
    minx, miny, maxx, maxy = rotated.bounds
    height = maxy - miny
    if height <= 0:
        return []

    sweep_positions: list[float] = []
    usable_spacing = max(corridor_spacing_m, clearance_m * 2.0, 0.5)
    if height <= usable_spacing:
        sweep_positions = [(miny + maxy) * 0.5]
    else:
        cursor = miny + usable_spacing * 0.5
        while cursor <= maxy - usable_spacing * 0.5 + 1e-6:
            sweep_positions.append(cursor)
            cursor += usable_spacing
        if not sweep_positions:
            sweep_positions = [(miny + maxy) * 0.5]

    corridors: list[WarehouseCorridor] = []
    for idx, y_pos in enumerate(sweep_positions):
        sweep_line = LineString(
            [
                (minx - usable_spacing * 2.0, y_pos),
                (maxx + usable_spacing * 2.0, y_pos),
            ]
        )
        clipped = rotated.intersection(sweep_line)
        for part_index, line in enumerate(_collect_lines(clipped)):
            coords = list(line.coords)
            if len(coords) < 2:
                continue
            start_xy, end_xy = coords[0], coords[-1]
            clipped_xy = _clip_segment_endpoints(
                start_xy=(float(start_xy[0]), float(start_xy[1])),
                end_xy=(float(end_xy[0]), float(end_xy[1])),
                trim_m=max(clearance_m, 0.0),
            )
            if clipped_xy is None:
                continue
            local_line = rotate_geometry(
                LineString([clipped_xy[0], clipped_xy[1]]),
                axis_deg,
                origin=(0, 0),
            )
            local_start_xy, local_end_xy = list(local_line.coords)
            heading = _normalize_angle_deg(
                _heading_deg(local_start_xy, local_end_xy)
            )
            corridors.append(
                WarehouseCorridor(
                    corridor_id=f"{source}_{len(corridors)}_{idx}_{part_index}",
                    start=WarehouseLocalPoint(
                        x_m=float(local_start_xy[0]),
                        y_m=float(local_start_xy[1]),
                        z_m=0.0,
                    ),
                    end=WarehouseLocalPoint(
                        x_m=float(local_end_xy[0]),
                        y_m=float(local_end_xy[1]),
                        z_m=0.0,
                    ),
                    width_m=float(width_m),
                    heading_deg=heading,
                    axis_deg=_normalize_angle_deg(axis_deg),
                    source=source,
                    sort_key=float(y_pos),
                )
            )
    return corridors


def _with_z(
        point: WarehouseLocalPoint,
        *,
        z_m: float,
        yaw_deg: Optional[float] = None,
) -> WarehouseLocalPoint:
    return WarehouseLocalPoint(
        x_m=float(point.x_m),
        y_m=float(point.y_m),
        z_m=float(z_m),
        yaw_deg=yaw_deg if yaw_deg is None else _normalize_angle_deg(yaw_deg),
    )


def _pass_segments_for_corridor(
        *,
        corridor: WarehouseCorridor,
        z_m: float,
        layer_index: int,
        view_mode: WarehouseViewMode,
        reverse: bool,
) -> list[WarehousePlanSegment]:
    base_start = corridor.end if reverse else corridor.start
    base_end = corridor.start if reverse else corridor.end
    heading = _normalize_angle_deg(
        _heading_deg((base_start.x_m, base_start.y_m), (base_end.x_m, base_end.y_m))
    )

    def _segment(
            *,
            segment_id: str,
            start_point: WarehouseLocalPoint,
            end_point: WarehouseLocalPoint,
            yaw_deg: Optional[float],
    ) -> WarehousePlanSegment:
        local_start = _with_z(start_point, z_m=z_m, yaw_deg=yaw_deg)
        local_end = _with_z(end_point, z_m=z_m, yaw_deg=yaw_deg)
        return WarehousePlanSegment(
            segment_id=segment_id,
            local_start=local_start,
            local_end=local_end,
            work_leg=True,
            leg_type="scan",
            yaw_deg=yaw_deg,
            layer_index=layer_index,
            corridor_id=corridor.corridor_id,
            source=corridor.source,
        )

    if view_mode == "dual_face":
        left_yaw = _normalize_angle_deg(heading + 90.0)
        right_yaw = _normalize_angle_deg(heading - 90.0)
        return [
            _segment(
                segment_id=f"{corridor.corridor_id}_layer_{layer_index}_left",
                start_point=base_start,
                end_point=base_end,
                yaw_deg=left_yaw,
            ),
            _segment(
                segment_id=f"{corridor.corridor_id}_layer_{layer_index}_right",
                start_point=base_end,
                end_point=base_start,
                yaw_deg=right_yaw,
            ),
        ]

    if view_mode == "left_face":
        yaw = _normalize_angle_deg(heading + 90.0)
    elif view_mode == "right_face":
        yaw = _normalize_angle_deg(heading - 90.0)
    else:
        yaw = heading

    return [
        _segment(
            segment_id=f"{corridor.corridor_id}_layer_{layer_index}",
            start_point=base_start,
            end_point=base_end,
            yaw_deg=yaw,
        )
    ]


def _append_segment_route(
        *,
        route_segments: list[WarehousePlanSegment],
        new_segments: Iterable[WarehousePlanSegment],
) -> None:
    for segment in new_segments:
        if route_segments and not _points_close(
                route_segments[-1].local_end,
                segment.local_start,
        ):
            transit = WarehousePlanSegment(
                segment_id=f"transit_{len(route_segments)}",
                local_start=route_segments[-1].local_end,
                local_end=segment.local_start,
                work_leg=False,
                leg_type="transit",
                yaw_deg=None,
                layer_index=segment.layer_index,
                corridor_id=segment.corridor_id,
                source="connector",
            )
            route_segments.append(transit)
        route_segments.append(segment)


def _segment_intersects_keepout(
        segment: WarehousePlanSegment,
        zone: WarehouseKeepoutZone,
) -> bool:
    if len(zone.footprint) < 3:
        return False
    min_z = float(zone.min_z_m) if zone.min_z_m is not None else None
    max_z = float(zone.max_z_m) if zone.max_z_m is not None else None
    seg_min_z = min(float(segment.local_start.z_m), float(segment.local_end.z_m))
    seg_max_z = max(float(segment.local_start.z_m), float(segment.local_end.z_m))
    if min_z is not None and seg_max_z < min_z:
        return False
    if max_z is not None and seg_min_z > max_z:
        return False
    line = LineString([
        (float(segment.local_start.x_m), float(segment.local_start.y_m)),
        (float(segment.local_end.x_m), float(segment.local_end.y_m)),
    ])
    poly = Polygon(zone.footprint)
    return line.intersects(poly)


def _segment_intersects_obstacle(
        segment: WarehousePlanSegment,
        obstacle: WarehouseObstacleBox,
) -> bool:
    half_x = float(obstacle.size_x_m) / 2.0
    half_y = float(obstacle.size_y_m) / 2.0
    min_z = float(obstacle.center.z_m) - (float(obstacle.size_z_m) / 2.0)
    max_z = float(obstacle.center.z_m) + (float(obstacle.size_z_m) / 2.0)
    seg_min_z = min(float(segment.local_start.z_m), float(segment.local_end.z_m))
    seg_max_z = max(float(segment.local_start.z_m), float(segment.local_end.z_m))
    if seg_max_z < min_z or seg_min_z > max_z:
        return False
    line = LineString([
        (float(segment.local_start.x_m), float(segment.local_start.y_m)),
        (float(segment.local_end.x_m), float(segment.local_end.y_m)),
    ])
    box = Polygon([
        (float(obstacle.center.x_m) - half_x, float(obstacle.center.y_m) - half_y),
        (float(obstacle.center.x_m) + half_x, float(obstacle.center.y_m) - half_y),
        (float(obstacle.center.x_m) + half_x, float(obstacle.center.y_m) + half_y),
        (float(obstacle.center.x_m) - half_x, float(obstacle.center.y_m) + half_y),
    ])
    return line.intersects(box)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def plan_warehouse_scan(
        *,
        polygon_local_m: list[tuple[float, float]],
        base_height_m: float,
        corridor_spacing_m: float,
        aisle_axis_deg: Optional[float],
        clearance_m: float,
        perimeter_offset_m: float,
        scan_pattern: WarehouseScanPattern,
        lane_strategy: WarehouseLaneStrategy,
        view_mode: WarehouseViewMode,
        layer_count: int,
        layer_spacing_m: float,
        ceiling_height_m: Optional[float],
        ceiling_margin_m: float,
        max_waypoints: int,
        max_route_m: float,
        dock_config: Optional[WarehouseDockConfig] = None,
        allow_inferred_dock: bool = True,
        obstacles_3d: Optional[list[WarehouseObstacleBox]] = None,
        keepout_zones: Optional[list[WarehouseKeepoutZone]] = None,
) -> WarehousePlanResult:
    """
    Plan a warehouse corridor scan entirely in the local metric frame.
    polygon_local_m is [[x_m, y_m], ...] relative to the dock/takeoff origin.
    No GPS coordinates are used or produced.
    """
    if len(polygon_local_m) < 3:
        raise ValueError("Warehouse polygon requires at least 3 points")

    footprint = Polygon(polygon_local_m)
    if not footprint.is_valid:
        raise ValueError("Warehouse footprint is invalid and cannot be planned")

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
    flyable_ring = [
        (float(x), float(y)) for x, y in flyable_polygon.exterior.coords[:-1]
    ]

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
    if ceiling_height_m is not None and top_layer_z + float(ceiling_margin_m) > float(ceiling_height_m):
        raise ValueError(
            "Warehouse scan layers exceed the configured ceiling clearance envelope"
        )

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
    dock_yaw_deg: Optional[float] = None
    dock_marker_id: Optional[str] = None
    precision_dock_required = False
    dock_inferred = False

    for layer in scan_layers:
        ordered_corridors = sorted(
            corridors,
            key=lambda item: (round(item.sort_key, 6), item.corridor_id),
        )
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
            raise ValueError("Warehouse dock pose is required when inferred dock planning is disabled")

        entry_segments: list[WarehousePlanSegment] = []
        if dock_point is not None and dock_exit_point is not None and not _points_close(dock_point, dock_exit_point):
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
        if exit_anchor is not None and not _points_close(exit_anchor, first_work_segment.local_start):
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
        if dock_point is not None and entry_anchor is not None and not _points_close(entry_anchor, dock_point):
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