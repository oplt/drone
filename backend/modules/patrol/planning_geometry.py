from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from shapely.geometry import MultiPolygon, Polygon

from backend.core.geometry.projection import (
    close_lonlat_ring,
    polygon_centroid_lonlat as _shared_polygon_centroid_lonlat,
)
from backend.modules.vehicle_runtime.types import Coordinate




def _ensure_closed_ring(
    points: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    return close_lonlat_ring(points)


def _poly_centroid_lonlat(
    poly_lonlat: Sequence[tuple[float, float]],
) -> tuple[float, float]:
    return _shared_polygon_centroid_lonlat(poly_lonlat)


def _largest_polygon(geometry: Polygon | MultiPolygon) -> Polygon | None:
    if isinstance(geometry, Polygon):
        return geometry if not geometry.is_empty else None
    if isinstance(geometry, MultiPolygon):
        if not geometry.geoms:
            return None
        return max(geometry.geoms, key=lambda g: g.area, default=None)
    return None


def _largest_viable_inward_offset(
    polygon: Polygon,
    *,
    requested_offset_m: float,
) -> tuple[Polygon | None, float]:
    """Find a smaller inward offset when the requested buffer collapses a small site."""
    requested = max(0.0, float(requested_offset_m))
    if requested <= 0.0 or polygon.area <= 0.0:
        return None, 0.0

    min_area_m2 = max(1.0, float(polygon.area) * 0.02)
    lo = 0.0
    hi = requested
    best_offset = 0.0
    best_polygon: Polygon | None = None

    for _ in range(16):
        mid = (lo + hi) / 2.0
        candidate = _largest_polygon(polygon.buffer(-mid))
        if candidate is not None and candidate.area >= min_area_m2:
            best_offset = mid
            best_polygon = candidate
            lo = mid
        else:
            hi = mid

    if best_polygon is None or best_offset < 0.25:
        return None, 0.0
    return best_polygon, float(best_offset)


def _ring_signed_area_xy(ring_xy: Sequence[tuple[float, float]]) -> float:
    if len(ring_xy) < 3:
        return 0.0
    area2 = 0.0
    for i in range(len(ring_xy)):
        x0, y0 = ring_xy[i]
        x1, y1 = ring_xy[(i + 1) % len(ring_xy)]
        area2 += (x0 * y1) - (x1 * y0)
    return area2 / 2.0


def _is_clockwise_xy(ring_xy: Sequence[tuple[float, float]]) -> bool:
    # Negative signed area => clockwise orientation.
    return _ring_signed_area_xy(ring_xy) < 0.0


def _polyline_length_m(points_xy: Sequence[tuple[float, float]]) -> float:
    if len(points_xy) < 2:
        return 0.0
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points_xy, points_xy[1:]):
        total += math.hypot(x2 - x1, y2 - y1)
    return float(total)


def _densify_ring_xy(
    ring_xy: Sequence[tuple[float, float]],
    *,
    max_segment_length_m: float,
) -> list[tuple[float, float]]:
    pts = list(ring_xy)
    if len(pts) < 3:
        return pts

    out: list[tuple[float, float]] = []
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(math.ceil(seg_len / max_segment_length_m)))

        for step in range(steps):
            t = step / steps
            px = x1 + (x2 - x1) * t
            py = y1 + (y2 - y1) * t
            if out and math.hypot(out[-1][0] - px, out[-1][1] - py) <= 0.01:
                continue
            out.append((px, py))

    if len(out) >= 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 0.01:
        out = out[:-1]

    return out


def _coords_close(a: Coordinate, b: Coordinate, tol: float = 1e-7) -> bool:
    return abs(float(a.lat) - float(b.lat)) <= tol and abs(float(a.lon) - float(b.lon)) <= tol


def _route_length_for_coords(coords: Sequence[Coordinate]) -> float:
    if len(coords) < 2:
        return 0.0

    lat0 = sum(float(p.lat) for p in coords) / len(coords)
    lon0 = sum(float(p.lon) for p in coords) / len(coords)
    xy = [_lonlat_to_xy_m(float(c.lon), float(c.lat), lon0, lat0) for c in coords]
    return _polyline_length_m(xy)


def _dynamic_trigger_profile(*, ai_tasks: Sequence[str], path_offset_m: float) -> dict[str, Any]:
    fence_buffer = max(2.0, min(15.0, float(path_offset_m) * 0.5 if path_offset_m > 0 else 6.0))
    return {
        "active_tasks": [str(t) for t in ai_tasks],
        "trigger_mode": "event_driven",
        "fence_breach_buffer_m": round(fence_buffer, 2),
        "verification_loiter_s": 20,
        "event_cooldown_s": 5,
    }
