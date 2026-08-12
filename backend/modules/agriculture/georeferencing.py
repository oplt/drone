from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class Pose:
    timestamp_utc: datetime
    lat: float
    lon: float
    altitude_m: float | None
    roll_deg: float | None
    pitch_deg: float | None
    yaw_deg: float | None
    gps_quality: float | None


@dataclass(frozen=True)
class InterpolationResult:
    pose: Pose | None
    status: str
    error_ms: float | None
    sample_ids: tuple[int | str, ...] = ()


def _sample_id(row: Any) -> int | str | None:
    value = getattr(row, "id", None)
    if value is None:
        return None
    if isinstance(value, (int, str)):
        return value
    return str(value)


def _sample_ids(*rows: Any) -> tuple[int | str, ...]:
    ids: list[int | str] = []
    for row in rows:
        sample_id = _sample_id(row)
        if sample_id is not None and sample_id not in ids:
            ids.append(sample_id)
    return tuple(ids)


def interpolate_pose(samples: Iterable[Any], timestamp_utc: datetime, max_gap_s: float = 5.0) -> InterpolationResult:
    rows = sorted(samples, key=lambda item: item.timestamp_utc)
    if not rows:
        return InterpolationResult(None, "unresolved", None)
    if timestamp_utc.tzinfo is None:
        timestamp_utc = timestamp_utc.replace(tzinfo=rows[0].timestamp_utc.tzinfo)
    before = None
    after = None
    for row in rows:
        if row.timestamp_utc <= timestamp_utc:
            before = row
        if row.timestamp_utc >= timestamp_utc:
            after = row
            break
    anchor = before or after
    if anchor is None:
        return InterpolationResult(None, "unresolved", None)
    if before is None or after is None or before.timestamp_utc == after.timestamp_utc:
        error_ms = abs((anchor.timestamp_utc - timestamp_utc).total_seconds()) * 1000
        if error_ms > max_gap_s * 1000:
            return InterpolationResult(None, "gap", error_ms, _sample_ids(anchor))
        return InterpolationResult(_pose(anchor), "nearest", error_ms, _sample_ids(anchor))
    span = (after.timestamp_utc - before.timestamp_utc).total_seconds()
    if span <= 0 or span > max_gap_s:
        error_ms = min(abs((timestamp_utc - before.timestamp_utc).total_seconds()), abs((after.timestamp_utc - timestamp_utc).total_seconds())) * 1000
        return InterpolationResult(None, "gap", error_ms, _sample_ids(before, after))
    ratio = (timestamp_utc - before.timestamp_utc).total_seconds() / span
    return InterpolationResult(
        _interpolate(before, after, ratio, timestamp_utc),
        "interpolated",
        0.0,
        _sample_ids(before, after),
    )


def _pose(row: Any) -> Pose:
    return Pose(row.timestamp_utc, float(row.lat), float(row.lon), row.relative_altitude_m or row.absolute_altitude_m, row.roll_deg, row.pitch_deg, row.yaw_deg, row.gps_quality)


def _lerp(a: float | None, b: float | None, ratio: float) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return float(a) + (float(b) - float(a)) * ratio


def _interpolate(a: Any, b: Any, ratio: float, timestamp_utc: datetime) -> Pose:
    return Pose(
        timestamp_utc,
        float(a.lat) + (float(b.lat) - float(a.lat)) * ratio,
        float(a.lon) + (float(b.lon) - float(a.lon)) * ratio,
        _lerp(a.relative_altitude_m or a.absolute_altitude_m, b.relative_altitude_m or b.absolute_altitude_m, ratio),
        _lerp(a.roll_deg, b.roll_deg, ratio),
        _lerp(a.pitch_deg, b.pitch_deg, ratio),
        _lerp(a.yaw_deg, b.yaw_deg, ratio),
        _lerp(a.gps_quality, b.gps_quality, ratio),
    )


def frame_footprint(*, pose: Pose, width_px: int, height_px: int, fov_h_deg: float, fov_v_deg: float) -> dict[str, Any]:
    """Return nadir ground footprint + GSD. Oblique/terrain correction deferred."""
    if pose.altitude_m is None or pose.altitude_m <= 0:
        return {"status": "unresolved", "reason": "missing_altitude"}
    width_m = 2 * pose.altitude_m * math.tan(math.radians(fov_h_deg / 2))
    height_m = 2 * pose.altitude_m * math.tan(math.radians(fov_v_deg / 2))
    cos_lat = max(0.1, math.cos(math.radians(pose.lat)))
    lat_delta = (height_m / 2) / 111_320
    lon_delta = (width_m / 2) / (111_320 * cos_lat)
    ring = [
        [pose.lon - lon_delta, pose.lat - lat_delta],
        [pose.lon + lon_delta, pose.lat - lat_delta],
        [pose.lon + lon_delta, pose.lat + lat_delta],
        [pose.lon - lon_delta, pose.lat + lat_delta],
        [pose.lon - lon_delta, pose.lat - lat_delta],
    ]
    return {
        "status": "resolved",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "width_m": width_m,
        "height_m": height_m,
        "gsd_cm": max(width_m / max(1, width_px), height_m / max(1, height_px)) * 100,
        "pose_status": "nadir_assumption",
    }
