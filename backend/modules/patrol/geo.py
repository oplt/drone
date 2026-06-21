from __future__ import annotations

from collections.abc import Sequence


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
