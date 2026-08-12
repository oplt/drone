from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def web_mercator_tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return an EPSG:4326 bbox for a Web Mercator XYZ tile."""
    n = 2**z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def geometry_coordinates(geometry: Any) -> list[tuple[float, float]]:
    if not isinstance(geometry, dict):
        return []
    def walk(value: Any) -> list[tuple[float, float]]:
        if isinstance(value, list) and len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            return [(float(value[0]), float(value[1]))]
        if isinstance(value, list):
            points: list[tuple[float, float]] = []
            for item in value:
                points.extend(walk(item))
            return points
        return []
    return walk(geometry.get("coordinates"))


def geometry_centroid(geometry: Any) -> tuple[float, float] | None:
    points = geometry_coordinates(geometry)
    if not points:
        return None
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def aggregate_features(rows: list[Any], *, zoom: int, max_features: int) -> tuple[dict[str, Any], bool]:
    """Create bounded point clusters while preserving raw geometries at high zoom."""
    should_cluster = zoom < 15 or len(rows) > max_features
    if not should_cluster:
        features = [
            {"type": "Feature", "geometry": row.geometry_geojson, "properties": {
                "observation_id": row.id, "observation_type": row.observation_type,
                "severity": row.severity, "confidence": row.confidence,
                "model_version": row.model_version,
                "provenance": getattr(row, "provenance", {}) or {},
                "cluster": False,
            }} for row in rows
        ]
        return {"type": "FeatureCollection", "features": features}, False

    # Grid size is intentionally stable per zoom so adjacent requests share cacheable output.
    cell_size = 360.0 / (2 ** max(1, min(zoom + 2, 22)))
    buckets: dict[tuple[int, int], list[Any]] = defaultdict(list)
    unresolved: list[Any] = []
    for row in rows:
        point = geometry_centroid(row.geometry_geojson)
        if point is None:
            unresolved.append(row)
            continue
        buckets[(math.floor((point[0] + 180) / cell_size), math.floor((point[1] + 90) / cell_size))].append(row)

    features: list[dict[str, Any]] = []
    for index, bucket in enumerate(buckets.values()):
        points = [geometry_centroid(row.geometry_geojson) for row in bucket]
        valid = [point for point in points if point is not None]
        lon = sum(point[0] for point in valid) / len(valid)
        lat = sum(point[1] for point in valid) / len(valid)
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {
            "id": f"cluster-{zoom}-{index}", "cluster": True, "count": len(bucket),
            "severity_min": min(row.severity for row in bucket),
            "severity_max": max(row.severity for row in bucket),
            "severity": sum(row.severity for row in bucket) / len(bucket),
            "confidence": sum(row.confidence for row in bucket) / len(bucket),
            "observation_types": sorted({row.observation_type for row in bucket}),
            "model_versions": sorted({row.model_version for row in bucket if row.model_version}),
        }})
    return {"type": "FeatureCollection", "features": features}, bool(unresolved)
