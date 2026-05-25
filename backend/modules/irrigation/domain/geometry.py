from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GeoBounds:
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def meters_per_degree_lat() -> float:
    return 111_320.0


def meters_per_degree_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def latlon_to_local_xy(
    *, lat: float, lon: float, origin_lat: float, origin_lon: float
) -> tuple[float, float]:
    return (
        (lon - origin_lon) * meters_per_degree_lon(origin_lat),
        (lat - origin_lat) * meters_per_degree_lat(),
    )


def local_xy_to_latlon(
    *, x_m: float, y_m: float, origin_lat: float, origin_lon: float
) -> tuple[float, float]:
    lat = origin_lat + (y_m / meters_per_degree_lat())
    lon_scale = meters_per_degree_lon(origin_lat)
    lon = origin_lon if lon_scale == 0 else origin_lon + (x_m / lon_scale)
    return lat, lon


def polygon_bbox(points: list[tuple[float, float]]) -> GeoBounds:
    lats = [lat for lat, _ in points]
    lons = [lon for _, lon in points]
    return GeoBounds(min(lats), min(lons), max(lats), max(lons))


def polygon_area_m2(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    origin_lat = points[0][0]
    origin_lon = points[0][1]
    xy = [
        latlon_to_local_xy(lat=lat, lon=lon, origin_lat=origin_lat, origin_lon=origin_lon)
        for lat, lon in points
    ]
    area_twice = 0.0
    for index, (x0, y0) in enumerate(xy):
        x1, y1 = xy[(index + 1) % len(xy)]
        area_twice += (x0 * y1) - (x1 * y0)
    return abs(area_twice) * 0.5
