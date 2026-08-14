"""Warehouse live-map bridge — CLI PointCloud2 sampling."""

from __future__ import annotations

import json
import logging
import math
import struct
from pathlib import Path
from typing import Any

import yaml

from .constants import _POINTFIELD_DATATYPE_SIZE
from .ros_commands import _run_ros2_command
from .settings_helpers import _setting_int

logger = logging.getLogger(__name__)


def _read_pointcloud2_yaml(*, topic: str, ws: Path) -> dict[str, Any] | None:
    """
    Development bridge: reads one PointCloud2 sample via ROS CLI and parses YAML.

    This is expensive for large PointCloud2 messages. Prefer the persistent rclpy
    subscribers used by the raw/colored/nvblox live-map bridges for production.
    """
    result = _run_ros2_command(
        ws=ws,
        ros_args=("topic", "echo", topic, "--once", "--full-length"),
        shell_timeout_s=2.0,
        process_timeout_s=4.0,
    )
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        payload = next(
            (doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)),
            None,
        )
    except Exception:
        logger.debug("Could not parse PointCloud2 YAML from %s", topic, exc_info=True)
        return None

    return payload


def _unpack_field(
    raw: bytes,
    *,
    offset: int,
    datatype: int,
    little_endian: bool,
) -> float | None:
    prefix = "<" if little_endian else ">"

    try:
        if datatype == 1:
            return float(struct.unpack_from(prefix + "b", raw, offset)[0])
        if datatype == 2:
            return float(struct.unpack_from(prefix + "B", raw, offset)[0])
        if datatype == 3:
            return float(struct.unpack_from(prefix + "h", raw, offset)[0])
        if datatype == 4:
            return float(struct.unpack_from(prefix + "H", raw, offset)[0])
        if datatype == 5:
            return float(struct.unpack_from(prefix + "i", raw, offset)[0])
        if datatype == 6:
            return float(struct.unpack_from(prefix + "I", raw, offset)[0])
        if datatype == 7:
            return float(struct.unpack_from(prefix + "f", raw, offset)[0])
        if datatype == 8:
            return float(struct.unpack_from(prefix + "d", raw, offset)[0])
    except (struct.error, ValueError):
        return None

    return None


def _field_spec(
    field: dict[str, Any],
    *,
    point_step: int,
) -> tuple[int, int] | None:
    try:
        offset = int(field["offset"])
        datatype = int(field["datatype"])
    except (KeyError, TypeError, ValueError):
        return None

    size = _POINTFIELD_DATATYPE_SIZE.get(datatype)
    if size is None or offset < 0 or offset + size > point_step:
        return None
    return offset, datatype


def _pointcloud2_to_chunk(
    payload: dict[str, Any],
    *,
    flight_id: str,
    sequence: int,
    max_points: int,
    source_topic: str = "/nvblox_node/static_esdf_pointcloud",
) -> dict[str, Any] | None:
    del flight_id
    fields = payload.get("fields")
    data = payload.get("data")
    point_step_raw = payload.get("point_step")
    is_bigendian = bool(payload.get("is_bigendian", False))

    if not isinstance(fields, list) or not isinstance(data, list):
        return None

    try:
        point_step = int(point_step_raw)
    except (TypeError, ValueError):
        return None

    if point_step <= 0:
        return None

    field_by_name: dict[str, dict[str, Any]] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        if name:
            field_by_name[name] = field

    if not all(name in field_by_name for name in ("x", "y", "z")):
        return None

    try:
        raw = bytes(int(value) & 0xFF for value in data)
    except (TypeError, ValueError):
        return None

    total_points = len(raw) // point_step
    if total_points <= 0:
        return None

    max_preview_points = max(1, int(max_points))
    stride = max(1, math.ceil(total_points / max_preview_points))
    little_endian = not is_bigendian

    x_spec = _field_spec(field_by_name["x"], point_step=point_step)
    y_spec = _field_spec(field_by_name["y"], point_step=point_step)
    z_spec = _field_spec(field_by_name["z"], point_step=point_step)
    if x_spec is None or y_spec is None or z_spec is None:
        return None

    x_offset, x_type = x_spec
    y_offset, y_type = y_spec
    z_offset, z_type = z_spec

    sampled: list[list[float]] = []
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    for index in range(0, total_points, stride):
        base = index * point_step
        x = _unpack_field(raw, offset=base + x_offset, datatype=x_type, little_endian=little_endian)
        y = _unpack_field(raw, offset=base + y_offset, datatype=y_type, little_endian=little_endian)
        z = _unpack_field(raw, offset=base + z_offset, datatype=z_type, little_endian=little_endian)

        if x is None or y is None or z is None:
            continue
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue

        sampled.append([round(x, 3), round(y, 3), round(z, 3)])
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        min_z = min(min_z, z)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        max_z = max(max_z, z)

        if len(sampled) >= max_preview_points:
            break

    if not sampled:
        return None

    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    frame_id = str(header.get("frame_id") or "").strip()
    if not frame_id:
        return None
    chunk_payload = {
        "format": "xyz_preview_v1",
        "frame_id": frame_id,
        "source_topic": source_topic,
        "sampled_point_count": len(sampled),
        "source_point_count": total_points,
        "points": sampled,
    }
    chunk_json = json.dumps(chunk_payload, separators=(",", ":")).encode("utf-8")

    return {
        "id": f"nvblox_esdf_{sequence:08d}",
        "kind": "point_cloud",
        "sequence": sequence,
        "point_count": total_points,
        "byte_size": len(chunk_json),
        "content_type": "application/json",
        "bbox_local_m": [
            round(min_x, 3),
            round(min_y, 3),
            round(min_z, 3),
            round(max_x, 3),
            round(max_y, 3),
            round(max_z, 3),
        ],
        "preview_points_m": sampled,
        "source": "nvblox_esdf",
        "layer": "esdf",
        "source_topic": source_topic,
    }


def _read_nvblox_chunk(
    *,
    flight_id: str,
    topic: str,
    ws: Path,
    sequence: int,
) -> dict[str, Any] | None:
    payload = _read_pointcloud2_yaml(topic=topic, ws=ws)
    if payload is None:
        return None

    max_points = _setting_int("warehouse_live_map_max_preview_points", 500, minimum=100)
    return _pointcloud2_to_chunk(
        payload,
        flight_id=flight_id,
        sequence=sequence,
        max_points=max_points,
        source_topic=topic,
    )


__all__ = ["_pointcloud2_to_chunk", "_read_nvblox_chunk", "_read_pointcloud2_yaml"]
