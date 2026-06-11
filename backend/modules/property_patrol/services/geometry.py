from __future__ import annotations

from typing import Any

from shapely.geometry import Point, Polygon, shape
from shapely.validation import explain_validity


def polygon_from_geojson(value: dict[str, Any], *, name: str) -> Polygon:
    try:
        geom = shape(value)
    except Exception as exc:
        raise ValueError(f"{name} is not valid GeoJSON: {exc}") from exc
    if geom.geom_type != "Polygon":
        raise ValueError(f"{name} must be a Polygon")
    poly = Polygon(geom.exterior.coords, [ring.coords for ring in geom.interiors])
    if not poly.is_valid:
        raise ValueError(f"{name} invalid: {explain_validity(poly)}")
    if poly.area <= 0:
        raise ValueError(f"{name} invalid: zero area")
    return poly


def polygons_from_geojson(values: list[dict[str, Any]], *, name: str) -> list[Polygon]:
    return [polygon_from_geojson(value, name=f"{name}[{idx}]") for idx, value in enumerate(values)]


def point_from_lat_lon(lat: float, lon: float) -> Point:
    return Point(float(lon), float(lat))


def waypoint_dict(lat: float, lon: float, alt: float, **extra: Any) -> dict[str, Any]:
    payload = {"lat": float(lat), "lon": float(lon), "alt": float(alt)}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload

