"""PointCloud2 parser — ROS message and YAML entry points."""

from __future__ import annotations

from typing import Any

from .coercion import _normalise_frame_id, _safe_int
from .parse_binary import _parse_pointcloud2_binary
from .fields import _field_map_from_msg, _field_map_from_yaml


def parse_pointcloud2_msg(
    msg: Any,
    *,
    max_points: int = 30_000,
    max_range_m: float | None = 80.0,
    min_range_m: float = 0.05,
    downsample: bool = True,
    fallback_color_mode: str = "height",
):
    point_step = _safe_int(getattr(msg, "point_step", None))
    if point_step is None or point_step <= 0:
        return None
    try:
        raw_data = msg.data
        raw: bytes | bytearray | memoryview = (
            raw_data if isinstance(raw_data, (bytes, bytearray, memoryview)) else bytes(raw_data)
        )
    except (TypeError, ValueError):
        return None

    header = getattr(msg, "header", None)
    frame_id = _normalise_frame_id(getattr(header, "frame_id", None))
    if frame_id is None:
        return None
    field_map = _field_map_from_msg(msg)
    return _parse_pointcloud2_binary(
        raw=raw,
        field_map=field_map,
        point_step=point_step,
        is_bigendian=bool(getattr(msg, "is_bigendian", False)),
        frame_id=frame_id,
        max_points=max_points,
        max_range_m=max_range_m,
        min_range_m=min_range_m,
        downsample=downsample,
        fallback_color_mode=fallback_color_mode,
    )


def parse_pointcloud2_yaml(
    payload: dict[str, Any],
    *,
    max_points: int = 30_000,
    max_range_m: float | None = 80.0,
    min_range_m: float = 0.05,
    downsample: bool = True,
    fallback_color_mode: str = "height",
):
    data = payload.get("data")
    point_step = _safe_int(payload.get("point_step"))
    if not isinstance(data, list) or point_step is None or point_step <= 0:
        return None

    try:
        raw = bytes((int(value) & 0xFF) for value in data)
    except (TypeError, ValueError, OverflowError):
        return None

    field_map = _field_map_from_yaml(payload)
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    frame_id = _normalise_frame_id((header or {}).get("frame_id"))
    if frame_id is None:
        return None

    return _parse_pointcloud2_binary(
        raw=raw,
        field_map=field_map,
        point_step=point_step,
        is_bigendian=bool(payload.get("is_bigendian", False)),
        frame_id=frame_id,
        max_points=max_points,
        max_range_m=max_range_m,
        min_range_m=min_range_m,
        downsample=downsample,
        fallback_color_mode=fallback_color_mode,
    )


__all__ = ["parse_pointcloud2_msg", "parse_pointcloud2_yaml"]
