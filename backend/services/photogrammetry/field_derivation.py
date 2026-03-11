from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image


def _ratio_to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if numerator is not None and denominator not in {None, 0}:
        return float(numerator) / float(denominator)
    if isinstance(value, tuple) and len(value) == 2 and value[1] not in {0, 0.0}:
        return float(value[0]) / float(value[1])
    return None


def _decode_ref(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="ignore")
    return str(value or "").strip()


def _dms_to_decimal(values: Any, ref: Any) -> float | None:
    if not isinstance(values, (list, tuple)) or len(values) < 3:
        return None
    degrees = _ratio_to_float(values[0])
    minutes = _ratio_to_float(values[1])
    seconds = _ratio_to_float(values[2])
    if degrees is None or minutes is None or seconds is None:
        return None

    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    ref_str = _decode_ref(ref).upper()
    if ref_str in {"S", "W"}:
        decimal *= -1.0
    return decimal


def gps_decimal_from_exif_ifd(gps_ifd: Mapping[int, Any]) -> tuple[float, float] | None:
    lat = _dms_to_decimal(gps_ifd.get(2), gps_ifd.get(1))
    lon = _dms_to_decimal(gps_ifd.get(4), gps_ifd.get(3))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lon, lat)


def extract_image_gps_location(image_path: str | Path) -> tuple[float, float] | None:
    try:
        with Image.open(Path(image_path)) as image:
            exif = image.getexif()
            if not exif:
                return None
            try:
                gps_ifd = exif.get_ifd(0x8825)
            except Exception:
                gps_ifd = None
            if not isinstance(gps_ifd, Mapping):
                raw_gps = exif.get(34853)
                gps_ifd = raw_gps if isinstance(raw_gps, Mapping) else None
            if not isinstance(gps_ifd, Mapping):
                return None
            return gps_decimal_from_exif_ifd(gps_ifd)
    except Exception:
        return None


def collect_image_gps_locations(image_paths: Sequence[str | Path]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for image_path in image_paths:
        point = extract_image_gps_location(image_path)
        if point is not None:
            points.append(point)
    return points


def derive_field_ring_from_points(
    points: Sequence[tuple[float, float]],
    *,
    padding_m: float = 20.0,
    min_span_m: float = 20.0,
) -> list[list[float]] | None:
    normalized: list[tuple[float, float]] = []
    for lon, lat in points:
        if -180.0 <= float(lon) <= 180.0 and -90.0 <= float(lat) <= 90.0:
            normalized.append((float(lon), float(lat)))
    if not normalized:
        return None

    lons = [point[0] for point in normalized]
    lats = [point[1] for point in normalized]
    west = min(lons)
    east = max(lons)
    south = min(lats)
    north = max(lats)

    mean_lat = sum(lats) / len(lats)
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = max(111_320.0 * math.cos(math.radians(mean_lat)), 1e-6)

    pad_lat = max(0.0, float(padding_m)) / meters_per_degree_lat
    pad_lon = max(0.0, float(padding_m)) / meters_per_degree_lon
    min_span_lat = max(0.0, float(min_span_m)) / meters_per_degree_lat
    min_span_lon = max(0.0, float(min_span_m)) / meters_per_degree_lon

    west -= pad_lon
    east += pad_lon
    south -= pad_lat
    north += pad_lat

    if (east - west) < min_span_lon:
        extra = (min_span_lon - (east - west)) / 2.0
        west -= extra
        east += extra
    if (north - south) < min_span_lat:
        extra = (min_span_lat - (north - south)) / 2.0
        south -= extra
        north += extra

    west = max(-180.0, west)
    east = min(180.0, east)
    south = max(-90.0, south)
    north = min(90.0, north)
    if east <= west or north <= south:
        return None

    return [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
    ]


def _extract_lonlat_pairs(node: Any) -> list[tuple[float, float]]:
    if isinstance(node, (list, tuple)):
        if (
            len(node) >= 2
            and isinstance(node[0], (int, float))
            and isinstance(node[1], (int, float))
        ):
            return [(float(node[0]), float(node[1]))]
        out: list[tuple[float, float]] = []
        for child in node:
            out.extend(_extract_lonlat_pairs(child))
        return out
    return []


def derive_field_ring_from_bbox_wgs84(
    bbox_wgs84: Mapping[str, Any] | None,
    *,
    padding_m: float = 0.0,
) -> list[list[float]] | None:
    if not isinstance(bbox_wgs84, Mapping):
        return None

    direct_keys = {"west", "south", "east", "north"}
    if direct_keys.issubset(bbox_wgs84.keys()):
        west = float(bbox_wgs84["west"])
        south = float(bbox_wgs84["south"])
        east = float(bbox_wgs84["east"])
        north = float(bbox_wgs84["north"])
        if east <= west or north <= south:
            return None
        return derive_field_ring_from_points(
            [(west, south), (east, north)],
            padding_m=padding_m,
            min_span_m=0.0,
        )

    points = _extract_lonlat_pairs(bbox_wgs84.get("coordinates"))
    if not points:
        return None
    return derive_field_ring_from_points(points, padding_m=padding_m, min_span_m=0.0)


def ring_to_polygon_wkt(ring: Sequence[Sequence[float]]) -> str:
    coords = [[float(lon), float(lat)] for lon, lat in ring]
    if len(coords) < 3:
        raise ValueError("Polygon ring requires at least 3 points")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    points = ", ".join(f"{lon} {lat}" for lon, lat in coords)
    return f"POLYGON(({points}))"
