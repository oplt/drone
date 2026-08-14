from __future__ import annotations

import logging
from collections.abc import Sequence

from shapely.geometry import Polygon

from backend.core.geometry.algorithm_runtime import profiled_geometry_plan
from backend.core.geometry.projection import (
    lonlat_to_xy_m as _lonlat_to_xy_m,
)
from backend.core.geometry.projection import (
    strip_closed_ring as _strip_closed_ring,
)
from backend.core.geometry.projection import (
    xy_m_to_lonlat as _xy_m_to_lonlat,
)
from backend.modules.patrol.planning.geometry import (
    densify_ring_xy,
    ensure_closed_ring,
    is_clockwise_xy,
    largest_polygon,
    largest_viable_inward_offset,
    poly_centroid_lonlat,
    polyline_length_m,
)
from backend.modules.patrol.planning.models import PrivatePatrolPlan
from backend.modules.patrol.planning.types import MAX_PRIVATE_PATROL_PATH_POINTS, PatrolDirection
from backend.modules.vehicle_runtime.types import Coordinate

logger = logging.getLogger(__name__)


@profiled_geometry_plan("private_patrol_plan")
def generate_private_patrol_plan(
    polygon_lonlat: Sequence[tuple[float, float]],
    *,
    altitude_agl_m: float,
    path_offset_m: float,
    direction: PatrolDirection,
    max_segment_length_m: float,
) -> PrivatePatrolPlan:
    """Convert a property polygon to an offset flyable perimeter path."""
    if len(polygon_lonlat) < 3:
        raise ValueError("property polygon must have at least 3 vertices")

    offset_m = float(path_offset_m)
    if offset_m < 0:
        raise ValueError("path_offset_m must be >= 0")

    segment_len_m = float(max_segment_length_m)
    if segment_len_m <= 0:
        raise ValueError("max_segment_length_m must be > 0")

    lonlat_ring = ensure_closed_ring([(float(lon), float(lat)) for lon, lat in polygon_lonlat])
    lon0, lat0 = poly_centroid_lonlat(lonlat_ring)

    xy_ring = [_lonlat_to_xy_m(lon, lat, lon0, lat0) for lon, lat in lonlat_ring]
    base_poly = Polygon(xy_ring)
    if not base_poly.is_valid or base_poly.area <= 0:
        raise ValueError("Invalid property polygon (self-intersection or zero area)")

    patrol_poly = base_poly
    applied_offset_m = 0.0

    if offset_m > 0:
        offset_candidate = largest_polygon(base_poly.buffer(-offset_m))
        if offset_candidate is not None and offset_candidate.area > 0:
            patrol_poly = offset_candidate
            applied_offset_m = offset_m
        else:
            offset_candidate, reduced_offset_m = largest_viable_inward_offset(
                base_poly,
                requested_offset_m=offset_m,
            )
            if offset_candidate is not None:
                patrol_poly = offset_candidate
                applied_offset_m = reduced_offset_m
            else:
                logger.warning(
                    "PrivatePatrol: inward offset %.2fm removed polygon; falling back to boundary path",
                    offset_m,
                )

    ring_xy = _strip_closed_ring([(float(x), float(y)) for x, y in patrol_poly.exterior.coords])
    if len(ring_xy) < 3:
        raise ValueError("Patrol route has fewer than 3 points after offset")

    clockwise = is_clockwise_xy(ring_xy)
    if (direction == "clockwise" and not clockwise) or (
        direction == "counterclockwise" and clockwise
    ):
        ring_xy = list(reversed(ring_xy))

    dense_xy = densify_ring_xy(ring_xy, max_segment_length_m=segment_len_m)
    if len(dense_xy) < 3:
        raise ValueError("Patrol route generation failed: too few route points")

    closed_dense_xy = dense_xy + [dense_xy[0]]
    waypoints: list[Coordinate] = []
    for x, y in closed_dense_xy:
        lon, lat = _xy_m_to_lonlat(x, y, lon0, lat0)
        waypoints.append(Coordinate(lat=lat, lon=lon, alt=float(altitude_agl_m)))

    route_m = polyline_length_m(closed_dense_xy)
    stats = {
        "direction": direction,
        "path_offset_requested_m": round(offset_m, 2),
        "path_offset_applied_m": round(applied_offset_m, 2),
        "raw_vertices": len(_strip_closed_ring(lonlat_ring)),
        "planned_vertices": len(dense_xy),
        "perimeter_m": round(route_m, 1),
        "area_m2": round(float(base_poly.area), 1),
        "limits": {
            "max_path_points": MAX_PRIVATE_PATROL_PATH_POINTS,
            "offset_retry_limit": 16,
        },
    }
    return PrivatePatrolPlan(waypoints=waypoints, stats=stats)
