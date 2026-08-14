from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import LineString, Polygon

from backend.modules.warehouse.planning.local_planner.models import WarehouseLocalPoint
from backend.modules.warehouse.planning.local_planner.types import (
    WarehouseLaneStrategy,
    WarehouseScanPattern,
    WarehouseViewMode,
)

def _distance_2d(a: WarehouseLocalPoint, b: WarehouseLocalPoint) -> float:
    return math.hypot(b.x_m - a.x_m, b.y_m - a.y_m)


def _distance_3d(a: WarehouseLocalPoint, b: WarehouseLocalPoint) -> float:
    return math.sqrt((b.x_m - a.x_m) ** 2 + (b.y_m - a.y_m) ** 2 + (b.z_m - a.z_m) ** 2)


def _points_close(
    a: WarehouseLocalPoint,
    b: WarehouseLocalPoint,
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


def _validate_finite_number(value: object, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _coerce_xy_ring(polygon_local_m: Sequence[Sequence[float] | tuple[float, float]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for idx, raw in enumerate(polygon_local_m):
        if len(raw) != 2:  # type: ignore[arg-type]
            raise ValueError(f"Warehouse polygon point {idx} must contain exactly [x_m, y_m]")
        x = _validate_finite_number(raw[0], name=f"polygon[{idx}].x_m")  # type: ignore[index]
        y = _validate_finite_number(raw[1], name=f"polygon[{idx}].y_m")  # type: ignore[index]
        points.append((x, y))
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3:
        raise ValueError("Warehouse polygon requires at least 3 distinct points")
    if len(set(points)) < 3:
        raise ValueError("Warehouse polygon requires at least 3 unique points")
    return points


def _validated_polygon(points: Sequence[tuple[float, float]]) -> Polygon:
    footprint = Polygon(points)
    if footprint.is_empty or footprint.area <= 0:
        raise ValueError("Warehouse footprint has zero area")
    if not footprint.is_valid:
        repaired = footprint.buffer(0)
        if repaired.is_empty or repaired.area <= 0 or not repaired.is_valid:
            raise ValueError("Warehouse footprint is invalid and cannot be planned")
        footprint = _largest_polygon(repaired)
    return footprint


def _normalize_scan_pattern(value: str) -> WarehouseScanPattern:
    allowed = {"aisle_serpentine", "stacked_passes", "crosshatch", "perimeter_aisle_hybrid"}
    if value not in allowed:
        raise ValueError(f"Unsupported warehouse scan pattern: {value!r}")
    return value  # type: ignore[return-value]


def _normalize_lane_strategy(value: str) -> WarehouseLaneStrategy:
    allowed = {"serpentine", "one_way"}
    if value not in allowed:
        raise ValueError(f"Unsupported warehouse lane strategy: {value!r}")
    return value  # type: ignore[return-value]


def _normalize_view_mode(value: str) -> WarehouseViewMode:
    allowed = {"forward", "left_face", "right_face", "dual_face"}
    if value not in allowed:
        raise ValueError(f"Unsupported warehouse view mode: {value!r}")
    return value  # type: ignore[return-value]
