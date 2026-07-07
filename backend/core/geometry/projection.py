from __future__ import annotations

import math
from collections.abc import Sequence


def meters_per_deg_lat() -> float:
    return 111_132.0


def meters_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def lonlat_to_xy_m(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    x = (lon - lon0) * meters_per_deg_lon(lat0)
    y = (lat - lat0) * meters_per_deg_lat()
    return x, y


def xy_m_to_lonlat(x: float, y: float, lon0: float, lat0: float) -> tuple[float, float]:
    lon = lon0 + x / meters_per_deg_lon(lat0)
    lat = lat0 + y / meters_per_deg_lat()
    return lon, lat


def strip_closed_ring(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [(float(lon), float(lat)) for lon, lat in points]
    if len(out) >= 2 and out[0] == out[-1]:
        return out[:-1]
    return out


def close_lonlat_ring(
    points: Sequence[tuple[float, float]],
    *,
    error_message: str = "polygon must have at least 3 points",
) -> list[tuple[float, float]]:
    if len(points) < 3:
        raise ValueError(error_message)
    out = [(float(lon), float(lat)) for lon, lat in points]
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def polygon_centroid_lonlat(
    polygon_lonlat: Sequence[tuple[float, float]],
    *,
    error_message: str = "polygon must have at least 3 points",
) -> tuple[float, float]:
    pts = strip_closed_ring(polygon_lonlat)
    if len(pts) < 3:
        raise ValueError(error_message)
    lon0 = sum(point[0] for point in pts) / len(pts)
    lat0 = sum(point[1] for point in pts) / len(pts)
    return lon0, lat0
