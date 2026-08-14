"""Metric stand-gap and plant-spacing analytics from geolocated plant centres."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from itertools import pairwise
from math import cos, radians, sin
from statistics import median
from typing import Any

from shapely.geometry import LineString, mapping


def _local(lon: float, lat: float, origin: tuple[float, float]) -> tuple[float, float]:
    return (
        (lon - origin[0]) * 111_320 * cos(radians(origin[1])),
        (lat - origin[1]) * 110_574,
    )


def _wgs84(x: float, y: float, origin: tuple[float, float]) -> tuple[float, float]:
    return (
        origin[0] + x / (111_320 * cos(radians(origin[1]))),
        origin[1] + y / 110_574,
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _spacing_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "status": "warning",
            "sample_count": 0,
            "median_spacing_m": None,
            "dispersion_iqr_m": None,
            "median_absolute_deviation_m": None,
            "statistical_outlier_count": 0,
            "warning": "insufficient_adjacent_plant_pairs",
        }
    middle = median(values)
    q1 = _percentile(values, 0.25) or 0.0
    q3 = _percentile(values, 0.75) or 0.0
    iqr = q3 - q1
    statistical_limit = q3 + 1.5 * iqr
    return {
        "status": "pass",
        "sample_count": len(values),
        "median_spacing_m": middle,
        "dispersion_iqr_m": iqr,
        "median_absolute_deviation_m": median([abs(value - middle) for value in values]),
        "q1_spacing_m": q1,
        "q3_spacing_m": q3,
        "statistical_outlier_threshold_m": statistical_limit,
        "statistical_outlier_count": sum(value > statistical_limit for value in values),
    }


def _plant_centres(detections: Iterable[Any]) -> tuple[list[dict[str, Any]], float]:
    located = [row for row in detections if row.lat is not None and row.lon is not None]
    groups: dict[str, list[Any]] = defaultdict(list)
    tracked = 0
    for index, row in enumerate(located):
        track_id = getattr(row, "track_id", None)
        if track_id is not None:
            tracked += 1
            key = f"track:{getattr(row, 'job_id', '')}:{track_id}"
        else:
            key = f"detection:{getattr(row, 'id', index)}"
        groups[key].append(row)
    centres = []
    for rows in groups.values():
        centres.append(
            {
                "lon": median([float(row.lon) for row in rows]),
                "lat": median([float(row.lat) for row in rows]),
                "confidence": sum(float(getattr(row, "confidence", 0.5)) for row in rows)
                / len(rows),
                "evidence_ids": [
                    str(getattr(row, "id", "")) for row in rows if getattr(row, "id", None)
                ],
            }
        )
    tracked_fraction = tracked / len(located) if located else 0.0
    return centres, tracked_fraction


def _gap_polygon(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    row_spacing_m: float,
    origin: tuple[float, float],
) -> tuple[dict[str, Any], float]:
    local = LineString([start, end]).buffer(max(0.05, row_spacing_m / 2), cap_style=2)
    geometry = mapping(local)

    def convert(value: Any) -> Any:
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(item, (int, float)) for item in value)
        ):
            return list(_wgs84(float(value[0]), float(value[1]), origin))
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    return (
        {"type": geometry["type"], "coordinates": convert(geometry["coordinates"])},
        float(local.area),
    )


def summarize_stands(
    detections: Iterable[Any],
    *,
    row_spacing_m: float | None,
    row_direction_deg: float | None,
    expected_plant_spacing_m: float | None = None,
    crop_type: str | None = None,
    gap_multiplier: float = 1.75,
) -> dict[str, Any]:
    """Return stand gaps plus row/global spacing statistics.

    WGS84 plant centres provide the metric scale. Gap classification is disabled
    unless crop, row geometry, and expected within-row spacing are all explicit.
    """

    centres, tracked_fraction = _plant_centres(detections)
    if not centres:
        return {
            "status": "unresolved",
            "gap_status": "blocked",
            "reason": "georeferenced_plant_centres_missing",
            "quality_warnings": ["metric_geometry_unavailable"],
            "gaps": [],
            "rows": [],
            "spacing": _spacing_stats([]),
            "estimated_count": None,
        }
    missing_context = []
    if row_spacing_m is None:
        missing_context.append("expected_row_spacing_m_missing")
    if row_direction_deg is None:
        missing_context.append("row_direction_deg_missing")
    if not str(crop_type or "").strip():
        missing_context.append("crop_type_missing")
    if expected_plant_spacing_m is None:
        missing_context.append("expected_plant_spacing_m_missing")
    if row_spacing_m is None or row_direction_deg is None:
        return {
            "status": "warning",
            "gap_status": "blocked",
            "reason": "row_geometry_context_missing",
            "quality_warnings": missing_context,
            "gaps": [],
            "rows": [],
            "spacing": {
                **_spacing_stats([]),
                "warning": "row_geometry_required_for_metric_spacing",
            },
            "estimated_count": len(centres),
            "geometry_source": "georeferenced_plant_centres",
        }

    origin = (float(centres[0]["lon"]), float(centres[0]["lat"]))
    angle = radians(float(row_direction_deg))
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for centre in centres:
        x, y = _local(float(centre["lon"]), float(centre["lat"]), origin)
        along = x * cos(angle) + y * sin(angle)
        across = -x * sin(angle) + y * cos(angle)
        centre.update({"x": x, "y": y, "along": along, "across": across})
        grouped[round(across / float(row_spacing_m))].append(centre)

    gaps: list[dict[str, Any]] = []
    row_summaries: list[dict[str, Any]] = []
    all_spacings: list[float] = []
    gap_threshold = (
        float(expected_plant_spacing_m) * float(gap_multiplier)
        if expected_plant_spacing_m is not None
        else None
    )
    for row_key, row_centres in sorted(grouped.items()):
        ordered = sorted(row_centres, key=lambda item: float(item["along"]))
        spacings: list[float] = []
        for left, right in pairwise(ordered):
            distance = float(right["along"]) - float(left["along"])
            if distance <= 0:
                continue
            spacings.append(distance)
            all_spacings.append(distance)
            if gap_threshold is None or distance <= gap_threshold:
                continue
            geometry, area_m2 = _gap_polygon(
                (float(left["x"]), float(left["y"])),
                (float(right["x"]), float(right["y"])),
                row_spacing_m=float(row_spacing_m),
                origin=origin,
            )
            missing_estimate = max(1, round(distance / float(expected_plant_spacing_m)) - 1)
            confidence = min(float(left["confidence"]), float(right["confidence"]))
            if tracked_fraction < 0.8:
                confidence *= 0.75
            gaps.append(
                {
                    "row_id": str(row_key),
                    "gap_length_m": distance,
                    "affected_area_m2": area_m2,
                    "estimated_missing_plants": missing_estimate,
                    "severity": min(1.0, missing_estimate / 4),
                    "confidence": max(0.0, min(1.0, confidence)),
                    "geometry_geojson": geometry,
                    "evidence_ids": [*left["evidence_ids"], *right["evidence_ids"]],
                }
            )
        row_summaries.append(
            {
                "row_id": str(row_key),
                "plant_count": len(ordered),
                "length_m": (
                    float(ordered[-1]["along"]) - float(ordered[0]["along"])
                    if len(ordered) > 1
                    else 0.0
                ),
                "gap_count": sum(item["row_id"] == str(row_key) for item in gaps),
                **_spacing_stats(spacings),
            }
        )

    quality_warnings = list(missing_context)
    if tracked_fraction < 0.8:
        quality_warnings.append("most_plant_centres_are_not_track_deduplicated")
    gap_status = "pass" if gap_threshold is not None and not missing_context else "blocked"
    return {
        "status": "pass" if not quality_warnings else "warning",
        "gap_status": gap_status,
        "estimated_count": len(centres),
        "row_count": len(grouped),
        "gap_count": len(gaps),
        "gap_segment_count": len(gaps),
        "double_cluster_count": 0,
        "gaps": gaps,
        "rows": row_summaries,
        "spacing": _spacing_stats(all_spacings),
        "quality_warnings": quality_warnings,
        "geometry_source": "georeferenced_plant_centres",
        "metric_distance_method": "local_wgs84_tangent_plane",
        "tracked_centre_fraction": tracked_fraction,
        "assumptions": {
            "crop_type": crop_type,
            "expected_row_spacing_m": row_spacing_m,
            "expected_plant_spacing_m": expected_plant_spacing_m,
            "row_direction_deg": row_direction_deg,
            "gap_multiplier": gap_multiplier,
            "gap_threshold_m": gap_threshold,
        },
    }
