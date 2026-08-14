"""Operational weed-density grids from geolocated, track-deduplicated detections."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from math import cos, floor, radians
from statistics import median
from typing import Any

from shapely.geometry import Point, box, mapping
from shapely.ops import transform


def _deduplicate(detections: Iterable[Any]) -> tuple[list[dict[str, Any]], float]:
    located = [row for row in detections if row.lat is not None and row.lon is not None]
    groups: dict[str, list[Any]] = defaultdict(list)
    tracked = 0
    for index, row in enumerate(located):
        track_id = getattr(row, "track_id", None)
        if track_id is None:
            key = f"detection:{getattr(row, 'id', index)}"
        else:
            tracked += 1
            key = f"track:{getattr(row, 'job_id', '')}:{track_id}"
        groups[key].append(row)
    weeds = [
        {
            "lon": median([float(row.lon) for row in rows]),
            "lat": median([float(row.lat) for row in rows]),
            "confidence": sum(float(getattr(row, "confidence", 0.5)) for row in rows) / len(rows),
            "evidence_ids": [
                str(getattr(row, "id", "")) for row in rows if getattr(row, "id", None)
            ],
        }
        for rows in groups.values()
    ]
    return weeds, tracked / len(located) if located else 0.0


def build_weed_density(
    detections: Iterable[Any],
    *,
    field_boundary_geojson: dict[str, Any] | None,
    cell_size_m: float = 10.0,
    hotspot_percentile: float = 0.8,
    previous_density_per_m2: float | None = None,
    previous_flight_id: str | None = None,
    max_cells: int = 50_000,
) -> dict[str, Any]:
    weeds, tracked_fraction = _deduplicate(detections)
    if not field_boundary_geojson:
        return {
            "status": "blocked",
            "reason": "field_boundary_missing",
            "geojson": {"type": "FeatureCollection", "features": []},
            "observations": [],
        }
    if cell_size_m <= 0 or not 0 < hotspot_percentile <= 1:
        return {
            "status": "blocked",
            "reason": "invalid_density_configuration",
            "geojson": {"type": "FeatureCollection", "features": []},
            "observations": [],
        }
    from shapely.geometry import shape

    boundary_wgs84 = shape(field_boundary_geojson)
    if boundary_wgs84.is_empty or not boundary_wgs84.is_valid:
        return {
            "status": "blocked",
            "reason": "field_boundary_invalid",
            "geojson": {"type": "FeatureCollection", "features": []},
            "observations": [],
        }
    origin = (float(boundary_wgs84.centroid.x), float(boundary_wgs84.centroid.y))
    scale_x = 111_320 * cos(radians(origin[1]))
    scale_y = 110_574

    def to_local(x, y, z=None):
        return ((x - origin[0]) * scale_x, (y - origin[1]) * scale_y)

    def to_wgs84(x, y, z=None):
        return (origin[0] + x / scale_x, origin[1] + y / scale_y)

    boundary = transform(to_local, boundary_wgs84)
    min_x, min_y, max_x, max_y = boundary.bounds
    column_count = max(1, int((max_x - min_x) // cell_size_m) + 1)
    row_count = max(1, int((max_y - min_y) // cell_size_m) + 1)
    if column_count * row_count > max_cells:
        return {
            "status": "blocked",
            "reason": "configured_density_grid_exceeds_cell_limit",
            "cell_count": column_count * row_count,
            "max_cells": max_cells,
            "geojson": {"type": "FeatureCollection", "features": []},
            "observations": [],
        }

    buckets: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    outside_count = 0
    for weed in weeds:
        point = Point(*to_local(float(weed["lon"]), float(weed["lat"])))
        if not boundary.covers(point):
            outside_count += 1
            continue
        key = (
            floor((point.x - min_x) / cell_size_m),
            floor((point.y - min_y) / cell_size_m),
        )
        buckets[key].append(weed)

    cells: list[dict[str, Any]] = []
    for column in range(column_count):
        for row in range(row_count):
            cell = box(
                min_x + column * cell_size_m,
                min_y + row * cell_size_m,
                min_x + (column + 1) * cell_size_m,
                min_y + (row + 1) * cell_size_m,
            ).intersection(boundary)
            if cell.is_empty or cell.area < 0.01:
                continue
            rows = buckets.get((column, row), [])
            cells.append(
                {
                    "key": (column, row),
                    "geometry": cell,
                    "area_m2": float(cell.area),
                    "rows": rows,
                    "density": len(rows) / float(cell.area),
                }
            )
    densities = sorted(float(cell["density"]) for cell in cells)
    nonempty_features = []
    observations = []
    for rank, cell in enumerate(sorted(cells, key=lambda item: item["density"], reverse=True), 1):
        if not cell["rows"]:
            continue
        percentile = sum(value <= cell["density"] for value in densities) / max(1, len(densities))
        is_hotspot = percentile >= hotspot_percentile
        geometry = mapping(transform(to_wgs84, cell["geometry"]))
        evidence_ids = [item for row in cell["rows"] for item in row["evidence_ids"]]
        confidence = sum(float(row["confidence"]) for row in cell["rows"]) / len(cell["rows"])
        if tracked_fraction < 0.8:
            confidence *= 0.75
        properties = {
            "detections": len(cell["rows"]),
            "area_m2": cell["area_m2"],
            "detections_per_m2": cell["density"],
            "field_percentile": percentile,
            "field_rank": rank,
            "field_cell_count": len(cells),
            "hotspot": is_hotspot,
            "confidence": max(0.0, min(1.0, confidence)),
        }
        nonempty_features.append(
            {"type": "Feature", "geometry": geometry, "properties": properties}
        )
        if is_hotspot:
            observations.append(
                {
                    "geometry_geojson": geometry,
                    "area_m2": cell["area_m2"],
                    "severity": percentile,
                    "confidence": properties["confidence"],
                    "evidence_ids": evidence_ids,
                    "sensor_values": properties,
                }
            )
    field_area = float(boundary.area)
    field_density = sum(len(cell["rows"]) for cell in cells) / field_area if field_area else 0.0
    change = None
    if previous_density_per_m2 is not None:
        change = {
            "previous_flight_id": previous_flight_id,
            "previous_detections_per_m2": previous_density_per_m2,
            "delta_detections_per_m2": field_density - previous_density_per_m2,
            "relative_change": (
                (field_density - previous_density_per_m2) / previous_density_per_m2
                if previous_density_per_m2 > 0
                else None
            ),
            "comparison_basis": "explicit_same_field_baseline_flight",
        }
    warnings = []
    if tracked_fraction < 0.8 and weeds:
        warnings.append("most_weed_centres_are_not_track_deduplicated")
    return {
        "status": "pass" if weeds else "not_measured",
        "reason": None if weeds else "georeferenced_weed_detections_missing",
        "geojson": {"type": "FeatureCollection", "features": nonempty_features},
        "observations": observations,
        "summary": {
            "units": "detections/m²",
            "unique_detection_count": sum(len(cell["rows"]) for cell in cells),
            "outside_field_count": outside_count,
            "field_area_m2": field_area,
            "field_density_detections_per_m2": field_density,
            "occupied_cell_count": len(nonempty_features),
            "field_cell_count": len(cells),
            "hotspot_count": len(observations),
            "cell_size_m": cell_size_m,
            "hotspot_percentile_threshold": hotspot_percentile,
            "tracked_centre_fraction": tracked_fraction,
            "deduplication": "job_track_id_or_detection_id",
            "quality_warnings": warnings,
            "change_vs_previous": change,
        },
    }
