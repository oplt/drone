"""Spatial/temporal aggregation of frame detections into farmer-facing issues."""

from collections.abc import Iterable
from datetime import UTC, datetime
from math import cos, radians
from typing import Any

from shapely.geometry import MultiPoint, mapping


def observation_type(label: str, capability_id: str | None = None) -> str:
    if capability_id == "fruit_counting":
        return "fruit_count"
    if capability_id == "ripeness_classification":
        return "ripeness_classification"
    normalized = label.lower().replace("-", "_").replace(" ", "_")
    if any(token in normalized for token in ("gap", "skip", "double", "overcrowd", "discontinu")):
        return "emergence_issue"
    if any(token in normalized for token in ("weed", "vegetation")):
        return "weed"
    if any(token in normalized for token in ("water", "flood", "drain")):
        return "standing_water"
    if any(token in normalized for token in ("plant", "crop", "stand")):
        return "stand_count"
    if any(token in normalized for token in ("stress", "anomaly", "disease")):
        return "abnormal_crop_health_signature"
    return "agriculture_anomaly"


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat0 = radians((a[1] + b[1]) / 2)
    return (((a[0] - b[0]) * 111_320 * cos(lat0)) ** 2 + ((a[1] - b[1]) * 110_574) ** 2) ** 0.5


def _local_geometry(
    points: list[tuple[float, float]], radius_m: float = 2.0
) -> tuple[dict[str, Any], float]:
    if not points:
        return {}, 0.0
    lon0 = sum(point[0] for point in points) / len(points)
    lat0 = sum(point[1] for point in points) / len(points)
    scale_x = 111_320 * cos(radians(lat0))
    scale_y = 110_574
    local = [((lon - lon0) * scale_x, (lat - lat0) * scale_y) for lon, lat in points]
    shape = MultiPoint(local).convex_hull.buffer(radius_m)
    geo = mapping(shape)

    def convert(value: Any) -> Any:
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(item, (int, float)) for item in value)
        ):
            return [lon0 + float(value[0]) / scale_x, lat0 + float(value[1]) / scale_y]
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    geo["coordinates"] = convert(geo["coordinates"])
    return {"type": geo["type"], "coordinates": geo["coordinates"]}, float(shape.area)


def aggregate_detections(
    detections: Iterable[Any],
    *,
    cluster_radius_m: float = 8.0,
    capability_by_job_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for detection in sorted(
        detections, key=lambda row: (float(row.timestamp_seconds), str(row.id))
    ):
        job_id = str(getattr(detection, "job_id", ""))
        capability_id = (capability_by_job_id or {}).get(job_id)
        kind = observation_type(str(detection.label), capability_id)
        point = (
            (float(detection.lon), float(detection.lat))
            if detection.lon is not None and detection.lat is not None
            else None
        )
        track_id = getattr(detection, "track_id", None)
        track_key = f"{job_id}:{track_id}" if track_id is not None else None
        candidates = [
            group
            for group in groups
            if group["kind"] == kind
            and (
                (track_key is not None and track_key in group["track_ids"])
                or (
                    point is not None
                    and group["points"]
                    and min(_distance_m(point, item) for item in group["points"])
                    <= cluster_radius_m
                )
            )
        ]
        group = candidates[0] if candidates else None
        if group is None:
            group = {"kind": kind, "points": [], "detections": [], "track_ids": set()}
            groups.append(group)
        if point is not None:
            group["points"].append(point)
        if track_key is not None:
            group["track_ids"].add(track_key)
        group["detections"].append(detection)

    output: list[dict[str, Any]] = []
    for group in groups:
        rows = group["detections"]
        located = bool(group["points"])
        telemetry_qualities = [
            str((getattr(row, "raw", {}) or {}).get("telemetry_match_quality", "unresolved"))
            for row in rows
        ]
        low_spatial_confidence = any(
            quality.startswith("low_confidence") or quality == "unresolved"
            for quality in telemetry_qualities
        )
        geometry, area_m2 = _local_geometry(group["points"]) if located else ({}, None)
        confidence = max(0.0, min(1.0, sum(float(row.confidence) for row in rows) / len(rows)))
        severity = max(0.0, min(1.0, confidence * min(1.0, len(rows) / 5)))
        timestamps = [datetime.fromtimestamp(float(row.timestamp_seconds), tz=UTC) for row in rows]
        sensor_values: dict[str, Any] = {}
        if group["kind"] == "fruit_count":
            fully_tracked = all(getattr(row, "track_id", None) is not None for row in rows)
            sensor_values = {
                "visible_fruit_count": len(group["track_ids"]) if fully_tracked else None,
                "count_status": "pass" if fully_tracked else "blocked_tracking_required",
                "deduplication": "unique_track_id" if fully_tracked else "unavailable",
            }
        elif group["kind"] == "ripeness_classification":
            sensor_values = {
                "visible_class_detections": {
                    label: sum(str(row.label) == label for row in rows)
                    for label in sorted({str(row.label) for row in rows})
                },
                "interpretation": "released_crop_specific_visible_classes_only",
            }
        output.append(
            {
                "observation_type": group["kind"],
                "geometry_geojson": geometry,
                "georef_status": (
                    "low_confidence"
                    if located and low_spatial_confidence
                    else "resolved"
                    if located
                    else "unresolved"
                ),
                "area_m2": area_m2,
                "severity": severity,
                "confidence": confidence,
                "uncertainty": {
                    "cluster_radius_m": cluster_radius_m,
                    "detection_count": len(rows),
                    "georef": "frame_pose" if located else "missing_frame_pose",
                    "spatial_confidence": "low" if low_spatial_confidence else "standard",
                    "telemetry_match_qualities": sorted(set(telemetry_qualities)),
                    "area_m2": {
                        "method": "convex_hull_buffer",
                        "uncertainty_m2": round(3.14159 * cluster_radius_m**2, 3)
                        if located
                        else None,
                    },
                    "deduplication": "track_id_or_spatial_cluster",
                },
                "first_detected": min(timestamps),
                "last_detected": max(timestamps),
                "trend": "current",
                "evidence_ids": [str(row.id) for row in rows],
                "sensor_values": sensor_values,
                "model_version": next(
                    (
                        str((getattr(row, "raw", {}) or {}).get("model_version"))
                        for row in rows
                        if (getattr(row, "raw", {}) or {}).get("model_version")
                    ),
                    None,
                ),
            }
        )
    return sorted(
        output, key=lambda row: (-row["severity"], row["observation_type"], row["evidence_ids"][0])
    )
