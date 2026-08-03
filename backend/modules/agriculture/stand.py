"""Deterministic row-segment summaries from located plant detections."""

from math import cos, radians, sin
from typing import Any, Iterable


def _local(lon: float, lat: float, origin: tuple[float, float]) -> tuple[float, float]:
    return ((lon - origin[0]) * 111_320 * cos(radians(origin[1])), (lat - origin[1]) * 110_574)


def summarize_stands(detections: Iterable[Any], *, row_spacing_m: float | None, row_direction_deg: float | None, segment_length_m: float = 10.0) -> dict[str, Any]:
    rows = [row for row in detections if row.lat is not None and row.lon is not None]
    if not rows:
        return {"status": "unresolved", "reason": "plant_positions_missing", "segments": [], "estimated_count": None}
    origin = (float(rows[0].lon), float(rows[0].lat))
    angle = radians(float(row_direction_deg or 0.0))
    segments: dict[tuple[int, int], list[Any]] = {}
    for row in rows:
        x, y = _local(float(row.lon), float(row.lat), origin)
        along = x * cos(angle) + y * sin(angle)
        across = -x * sin(angle) + y * cos(angle)
        row_key = round(across / max(float(row_spacing_m or 3.0), 0.5))
        segment_key = (row_key, int(along // max(segment_length_m, 1.0)))
        segments.setdefault(segment_key, []).append(row)
    counts = [len(values) for values in segments.values()]
    by_row: dict[int, list[int]] = {}
    for row_key, segment_key in segments:
        by_row.setdefault(row_key, []).append(segment_key)
    gaps = [(row_key, index) for row_key, indexes in by_row.items() for index in range(min(indexes), max(indexes) + 1) if index not in indexes]
    doubles = [key for key, values in segments.items() if len(values) >= 2]
    return {
        "status": "pass", "segment_count": len(segments), "estimated_count": len(rows),
        "plants_per_segment": sum(counts) / max(1, len(counts)), "plants_per_hectare": len(rows),
        "establishment_pct": min(100.0, len(rows) / max(1.0, len(segments)) * 100.0),
        "gap_segment_count": len(gaps), "double_cluster_count": len(doubles),
        "uncertainty": {"row_spacing_m": row_spacing_m, "row_direction_deg": row_direction_deg, "segment_length_m": segment_length_m, "reason": "heuristic_segment_density"},
    }
