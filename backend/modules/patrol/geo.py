from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

from backend.core.geometry.projection import (
    lonlat_to_xy_m as _lonlat_to_xy_m,
    meters_per_deg_lat as _meters_per_deg_lat,
    meters_per_deg_lon as _meters_per_deg_lon,
    strip_closed_ring as _strip_closed_ring,
)


def point_in_polygon(
    lat: float,
    lon: float,
    polygon: Sequence[tuple[float, float]],
) -> bool:
    """Ray-casting point-in-polygon. Polygon vertices are (lon, lat)."""
    if len(polygon) < 3:
        return False

    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        lon_i, lat_i = float(polygon[i][0]), float(polygon[i][1])
        lon_j, lat_j = float(polygon[j][0]), float(polygon[j][1])
        intersects = (lat_i > lat) != (lat_j > lat) and lon < (
            (lon_j - lon_i) * (lat - lat_i) / ((lat_j - lat_i) or 1e-12) + lon_i
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def distance_point_to_polygon_m(
    lat: float,
    lon: float,
    polygon: Sequence[tuple[float, float]],
) -> float:
    """Meters from point to polygon edge. Returns 0 when inside or on the boundary."""
    pts = _strip_closed_ring([(float(lo), float(la)) for lo, la in polygon])
    if len(pts) < 3:
        return float("inf")

    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)

    pt = Point(float(lon), float(lat))
    if poly.covers(pt):
        return 0.0

    nearest = nearest_points(pt, poly)[1]
    px, py = _lonlat_to_xy_m(lon, lat, lon, lat)
    nx, ny = _lonlat_to_xy_m(nearest.x, nearest.y, lon, lat)
    return math.hypot(nx - px, ny - py)


def point_in_geofence_within_m(
    lat: float,
    lon: float,
    polygon: Sequence[tuple[float, float]],
    *,
    tolerance_m: float = 0.0,
) -> bool:
    return distance_point_to_polygon_m(lat, lon, polygon) <= max(0.0, float(tolerance_m))


def snap_point_inside_geofence(
    lat: float,
    lon: float,
    polygon: Sequence[tuple[float, float]],
) -> tuple[float, float]:
    """Move an exterior (or boundary) point to a nearby interior point."""
    if distance_point_to_polygon_m(lat, lon, polygon) == 0:
        return lat, lon

    pts = _strip_closed_ring([(float(lo), float(la)) for lo, la in polygon])
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)

    pt = Point(float(lon), float(lat))
    centroid = poly.centroid
    anchor = nearest_points(pt, poly)[1]

    for fraction in (0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0):
        candidate = Point(
            anchor.x + (centroid.x - anchor.x) * fraction,
            anchor.y + (centroid.y - anchor.y) * fraction,
        )
        if poly.contains(candidate):
            return float(candidate.y), float(candidate.x)

    return float(centroid.y), float(centroid.x)


def normalize_polygon_lonlat(
    polygon: Sequence[Sequence[float]] | None,
) -> tuple[tuple[float, float], ...]:
    if not polygon:
        return ()
    out: list[tuple[float, float]] = []
    for pt in polygon:
        if len(pt) < 2:
            continue
        out.append((float(pt[0]), float(pt[1])))
    return tuple(out)


def _point_to_segment_distance_m(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    """Shortest distance from point P to segment AB in local meters."""
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    ab_len_sq = abx * abx + aby * aby
    if ab_len_sq <= 1e-12:
        return math.hypot(apx, apy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_len_sq))
    closest_x = ax + t * abx
    closest_y = ay + t * aby
    return math.hypot(px - closest_x, py - closest_y)


def max_orbit_radius_inside_polygon(
    center_lon: float,
    center_lat: float,
    polygon_lonlat: Sequence[tuple[float, float]],
    *,
    requested_radius_m: float,
    safety_margin_m: float = 2.0,
) -> float:
    """Clamp an orbit radius so the full circle stays inside the geofence polygon."""
    requested = max(0.0, float(requested_radius_m))
    if requested <= 0.0:
        return 0.0

    pts = _strip_closed_ring(polygon_lonlat)
    if len(pts) < 3:
        return requested

    if not point_in_polygon(float(center_lat), float(center_lon), pts):
        return 0.0

    lon0 = float(center_lon)
    lat0 = float(center_lat)
    min_edge_dist_m = float("inf")
    for i in range(len(pts)):
        lon_a, lat_a = pts[i]
        lon_b, lat_b = pts[(i + 1) % len(pts)]
        ax, ay = _lonlat_to_xy_m(lon_a, lat_a, lon0, lat0)
        bx, by = _lonlat_to_xy_m(lon_b, lat_b, lon0, lat0)
        min_edge_dist_m = min(
            min_edge_dist_m,
            _point_to_segment_distance_m(0.0, 0.0, ax, ay, bx, by),
        )

    if not math.isfinite(min_edge_dist_m):
        return 0.0

    max_safe_radius_m = max(0.0, min_edge_dist_m - max(0.0, float(safety_margin_m)))
    return min(requested, max_safe_radius_m)


def generate_orbit_offsets_m(
    radius_m: float,
    *,
    segments: int = 8,
    direction: Literal["clockwise", "counterclockwise"] = "clockwise",
) -> list[tuple[float, float]]:
    """Return meter offsets for a closed orbit ring centered at the origin."""
    radius = max(0.0, float(radius_m))
    count = max(3, int(segments))
    if radius <= 0.0:
        return []

    step = (2.0 * math.pi) / count
    if direction == "clockwise":
        step = -step

    start_angle = math.pi / 2.0
    offsets: list[tuple[float, float]] = []
    for i in range(count):
        angle = start_angle + (step * i)
        offsets.append((radius * math.cos(angle), radius * math.sin(angle)))
    return offsets
