"""PointCloud2 parser — binary point cloud parsing."""

from __future__ import annotations

import math

import numpy as np

from .colors import (
    _decode_packed_rgb_array,
    _distance_colors,
    _height_distance_colors,
    _normalise_rgb_array,
)
from .constants import COLOR_FIELD_NAMES
from .coercion import _safe_float
from .fields import (
    _field_is_valid,
    _read_field_array,
    _unpack_field,
    detect_color_fields,
)
from .models import ParsedPointCloud


def _parse_pointcloud2_binary(
    *,
    raw: bytes | bytearray | memoryview,
    field_map: dict[str, tuple[int, int]],
    point_step: int,
    is_bigendian: bool,
    frame_id: str,
    max_points: int,
    max_range_m: float | None,
    min_range_m: float,
    downsample: bool,
    fallback_color_mode: str,
) -> ParsedPointCloud | None:
    if point_step <= 0:
        return None
    max_points = max(1, int(max_points or 1))
    min_range = max(0.0, _safe_float(min_range_m, default=0.0) or 0.0)
    max_range = None if max_range_m is None else _safe_float(max_range_m, default=None)

    required = ("x", "y", "z")
    if not all(_field_is_valid(field_map, name, point_step=point_step) for name in required):
        return None

    total_points = len(raw) // point_step
    if total_points <= 0:
        return None

    stride = 1
    if downsample and total_points > max_points:
        stride = max(1, math.ceil(total_points / max_points))
    sampled_indices = np.arange(0, total_points, stride, dtype=np.int64)

    parsed = _parse_pointcloud2_binary_vectorized(
        raw=raw,
        field_map=field_map,
        point_step=point_step,
        total_points=total_points,
        sampled_indices=sampled_indices,
        little_endian=not is_bigendian,
        frame_id=frame_id,
        max_points=max_points,
        max_range_m=max_range,
        min_range_m=min_range,
        fallback_color_mode=fallback_color_mode,
    )
    if parsed is not None:
        return parsed

    return _parse_pointcloud2_binary_generic(
        raw=raw,
        field_map=field_map,
        point_step=point_step,
        total_points=total_points,
        sampled_indices=sampled_indices,
        little_endian=not is_bigendian,
        frame_id=frame_id,
        max_points=max_points,
        max_range_m=max_range,
        min_range_m=min_range,
        fallback_color_mode=fallback_color_mode,
    )


def _parse_pointcloud2_binary_vectorized(
    *,
    raw: bytes | bytearray | memoryview,
    field_map: dict[str, tuple[int, int]],
    point_step: int,
    total_points: int,
    sampled_indices: np.ndarray,
    little_endian: bool,
    frame_id: str,
    max_points: int,
    max_range_m: float | None,
    min_range_m: float,
    fallback_color_mode: str,
) -> ParsedPointCloud | None:
    x_offset, x_type = field_map["x"]
    y_offset, y_type = field_map["y"]
    z_offset, z_type = field_map["z"]
    arrays = [
        _read_field_array(
            raw,
            offset=x_offset,
            datatype=x_type,
            point_step=point_step,
            total_points=total_points,
            little_endian=little_endian,
            indices=sampled_indices,
        ),
        _read_field_array(
            raw,
            offset=y_offset,
            datatype=y_type,
            point_step=point_step,
            total_points=total_points,
            little_endian=little_endian,
            indices=sampled_indices,
        ),
        _read_field_array(
            raw,
            offset=z_offset,
            datatype=z_type,
            point_step=point_step,
            total_points=total_points,
            little_endian=little_endian,
            indices=sampled_indices,
        ),
    ]
    if any(array is None for array in arrays):
        return None

    xyz = np.column_stack(arrays).astype(np.float32, copy=False)  # type: ignore[arg-type]
    finite = np.isfinite(xyz).all(axis=1)
    if not finite.any():
        return None
    distances = np.linalg.norm(xyz, axis=1)
    mask = finite & (distances >= min_range_m)
    if max_range_m is not None:
        mask &= distances <= max_range_m
    if not mask.any():
        return None
    chosen = np.flatnonzero(mask)[:max_points] if mask.sum() > max_points else np.flatnonzero(mask)
    xyz = np.ascontiguousarray(xyz[chosen], dtype=np.float32)
    original_indices = sampled_indices[chosen]

    rgb: np.ndarray | None = None
    has_rgb = False
    color_layout = detect_color_fields([{"name": name} for name in field_map])
    packed_name = (
        str(color_layout["field"])
        if color_layout is not None and color_layout.get("mode") == "packed"
        else None
    )
    if packed_name and _field_is_valid(field_map, packed_name, point_step=point_step):
        rgb_offset, rgb_type = field_map[packed_name]
        packed = _read_field_array(
            raw,
            offset=rgb_offset,
            datatype=rgb_type,
            point_step=point_step,
            total_points=total_points,
            little_endian=little_endian,
            indices=original_indices,
        )
        rgb = (
            _decode_packed_rgb_array(packed, mode=packed_name, datatype=rgb_type)
            if packed is not None
            else None
        )
        has_rgb = rgb is not None and rgb.shape[0] == xyz.shape[0]
    elif all(_field_is_valid(field_map, name, point_step=point_step) for name in ("r", "g", "b")):
        channels: list[np.ndarray] = []
        for name in ("r", "g", "b"):
            offset, datatype = field_map[name]
            channel = _read_field_array(
                raw,
                offset=offset,
                datatype=datatype,
                point_step=point_step,
                total_points=total_points,
                little_endian=little_endian,
                indices=original_indices,
            )
            if channel is None:
                channels = []
                break
            channels.append(channel)
        if len(channels) == 3:
            rgb = _normalise_rgb_array(np.column_stack(channels))
            has_rgb = rgb.shape[0] == xyz.shape[0]

    if not has_rgb:
        rgb = (
            _distance_colors(xyz)
            if fallback_color_mode == "distance"
            else _height_distance_colors(xyz)
        )

    intensity: np.ndarray | None = None
    if "intensity" in field_map and _field_is_valid(field_map, "intensity", point_step=point_step):
        intensity_offset, intensity_type = field_map["intensity"]
        values = _read_field_array(
            raw,
            offset=intensity_offset,
            datatype=intensity_type,
            point_step=point_step,
            total_points=total_points,
            little_endian=little_endian,
            indices=original_indices,
        )
        if values is not None:
            intensity = np.nan_to_num(
                values.astype(np.float32, copy=False), nan=0.0, posinf=0.0, neginf=0.0
            )

    return ParsedPointCloud(
        xyz=xyz,
        rgb=np.ascontiguousarray(rgb, dtype=np.float32) if rgb is not None else None,
        has_rgb=has_rgb,
        frame_id=frame_id,
        point_count=int(xyz.shape[0]),
        intensity=np.ascontiguousarray(intensity, dtype=np.float32)
        if intensity is not None
        else None,
        fields=tuple(field_map),
    )


def _parse_pointcloud2_binary_generic(
    *,
    raw: bytes | bytearray | memoryview,
    field_map: dict[str, tuple[int, int]],
    point_step: int,
    total_points: int,
    sampled_indices: np.ndarray,
    little_endian: bool,
    frame_id: str,
    max_points: int,
    max_range_m: float | None,
    min_range_m: float,
    fallback_color_mode: str,
) -> ParsedPointCloud | None:
    x_offset, x_type = field_map["x"]
    y_offset, y_type = field_map["y"]
    z_offset, z_type = field_map["z"]

    rgb_mode: str | None = None
    rgb_offset = rgb_type = None
    color_layout = detect_color_fields([{"name": name} for name in field_map])
    packed_name = (
        str(color_layout["field"])
        if color_layout is not None and color_layout.get("mode") == "packed"
        else None
    )
    if packed_name and _field_is_valid(field_map, packed_name, point_step=point_step):
        rgb_mode = packed_name
        rgb_offset, rgb_type = field_map[packed_name]
    elif all(_field_is_valid(field_map, name, point_step=point_step) for name in ("r", "g", "b")):
        rgb_mode = "separate"

    intensity_offset = intensity_type = None
    if "intensity" in field_map and _field_is_valid(field_map, "intensity", point_step=point_step):
        intensity_offset, intensity_type = field_map["intensity"]

    xyz_rows: list[list[float]] = []
    rgb_rows: list[list[float]] = []
    intensity_rows: list[float] = []

    for index in sampled_indices.tolist():
        base = index * point_step
        x = _unpack_field(raw, offset=base + x_offset, datatype=x_type, little_endian=little_endian)
        y = _unpack_field(raw, offset=base + y_offset, datatype=y_type, little_endian=little_endian)
        z = _unpack_field(raw, offset=base + z_offset, datatype=z_type, little_endian=little_endian)
        if x is None or y is None or z is None:
            continue
        xf = float(x)
        yf = float(y)
        zf = float(z)
        if not (math.isfinite(xf) and math.isfinite(yf) and math.isfinite(zf)):
            continue
        distance = math.sqrt(xf * xf + yf * yf + zf * zf)
        if distance < min_range_m:
            continue
        if max_range_m is not None and distance > max_range_m:
            continue

        xyz_rows.append([xf, yf, zf])

        if rgb_mode in COLOR_FIELD_NAMES and rgb_offset is not None and rgb_type is not None:
            packed = _unpack_field(
                raw, offset=base + rgb_offset, datatype=rgb_type, little_endian=little_endian
            )
            decoded_array = (
                _decode_packed_rgb_array(np.asarray([packed]), mode=rgb_mode, datatype=rgb_type)
                if packed is not None
                else None
            )
            decoded = decoded_array[0] if decoded_array is not None else None
            rgb_rows.append(list(decoded) if decoded is not None else [0.7, 0.7, 0.7])
        elif rgb_mode == "separate":
            values: list[float] = []
            for name in ("r", "g", "b"):
                offset, datatype = field_map[name]
                raw_value = _unpack_field(
                    raw, offset=base + offset, datatype=datatype, little_endian=little_endian
                )
                values.append(float(raw_value) if raw_value is not None else 0.7)
            rgb_rows.append(values)

        if intensity_offset is not None and intensity_type is not None:
            value = _unpack_field(
                raw,
                offset=base + intensity_offset,
                datatype=intensity_type,
                little_endian=little_endian,
            )
            ivalue = float(value) if value is not None else 0.0
            intensity_rows.append(ivalue if math.isfinite(ivalue) else 0.0)

        if len(xyz_rows) >= max_points:
            break

    if not xyz_rows:
        return None

    xyz = np.asarray(xyz_rows, dtype=np.float32)
    has_rgb = bool(rgb_rows) and len(rgb_rows) == xyz.shape[0]
    if has_rgb:
        rgb = _normalise_rgb_array(np.asarray(rgb_rows, dtype=np.float32))
    else:
        rgb = (
            _distance_colors(xyz)
            if fallback_color_mode == "distance"
            else _height_distance_colors(xyz)
        )

    intensity = None
    if intensity_rows and len(intensity_rows) == xyz.shape[0]:
        intensity = np.asarray(intensity_rows, dtype=np.float32)

    return ParsedPointCloud(
        xyz=np.ascontiguousarray(xyz, dtype=np.float32),
        rgb=np.ascontiguousarray(rgb, dtype=np.float32),
        has_rgb=has_rgb,
        frame_id=frame_id,
        point_count=int(xyz.shape[0]),
        intensity=np.ascontiguousarray(intensity, dtype=np.float32)
        if intensity is not None
        else None,
        fields=tuple(field_map),
    )


__all__ = ["_parse_pointcloud2_binary"]
