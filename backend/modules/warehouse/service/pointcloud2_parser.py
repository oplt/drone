from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Any

import numpy as np

_POINTFIELD_DATATYPE_SIZE: dict[int, int] = {
    1: 1,
    2: 1,
    3: 2,
    4: 2,
    5: 4,
    6: 4,
    7: 4,
    8: 8,
}


@dataclass(frozen=True)
class ParsedPointCloud:
    xyz: np.ndarray
    rgb: np.ndarray | None
    has_rgb: bool
    frame_id: str
    point_count: int
    intensity: np.ndarray | None = None


def _unpack_field(
    raw: bytes,
    *,
    offset: int,
    datatype: int,
    little_endian: bool,
) -> float | int | None:
    prefix = "<" if little_endian else ">"

    try:
        if datatype == 1:
            return struct.unpack_from(prefix + "b", raw, offset)[0]
        if datatype == 2:
            return struct.unpack_from(prefix + "B", raw, offset)[0]
        if datatype == 3:
            return struct.unpack_from(prefix + "h", raw, offset)[0]
        if datatype == 4:
            return struct.unpack_from(prefix + "H", raw, offset)[0]
        if datatype == 5:
            return struct.unpack_from(prefix + "i", raw, offset)[0]
        if datatype == 6:
            return struct.unpack_from(prefix + "I", raw, offset)[0]
        if datatype == 7:
            return struct.unpack_from(prefix + "f", raw, offset)[0]
        if datatype == 8:
            return struct.unpack_from(prefix + "d", raw, offset)[0]
    except (struct.error, ValueError, IndexError):
        return None

    return None


def _decode_rgb_packed(value: float | int) -> tuple[float, float, float] | None:
    if isinstance(value, float):
        packed = struct.unpack("I", struct.pack("f", value))[0]
    else:
        packed = int(value) & 0xFFFFFFFF

    r = ((packed >> 16) & 0xFF) / 255.0
    g = ((packed >> 8) & 0xFF) / 255.0
    b = (packed & 0xFF) / 255.0
    return (r, g, b)


def _decode_rgba_packed(value: float | int) -> tuple[float, float, float] | None:
    if isinstance(value, float):
        packed = struct.unpack("I", struct.pack("f", value))[0]
    else:
        packed = int(value) & 0xFFFFFFFF

    r = ((packed >> 24) & 0xFF) / 255.0
    g = ((packed >> 16) & 0xFF) / 255.0
    b = ((packed >> 8) & 0xFF) / 255.0
    return (r, g, b)


def _field_map_from_msg(msg: Any) -> dict[str, tuple[int, int]]:
    fields: dict[str, tuple[int, int]] = {}
    for field in msg.fields:
        name = str(getattr(field, "name", "") or "")
        if not name:
            continue
        fields[name] = (int(field.offset), int(field.datatype))
    return fields


def _field_map_from_yaml(payload: dict[str, Any]) -> dict[str, tuple[int, int]]:
    fields: dict[str, tuple[int, int]] = {}
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list):
        return fields
    for field in raw_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        if not name:
            continue
        try:
            fields[name] = (int(field["offset"]), int(field["datatype"]))
        except (KeyError, TypeError, ValueError):
            continue
    return fields


def _height_distance_colors(xyz: np.ndarray) -> np.ndarray:
    colors = np.zeros((xyz.shape[0], 3), dtype=np.float32)
    z = xyz[:, 2]
    min_z = float(np.nanmin(z)) if xyz.shape[0] else 0.0
    max_z = float(np.nanmax(z)) if xyz.shape[0] else 1.0
    span = max(0.001, max_z - min_z)
    t = np.clip((z - min_z) / span, 0.0, 1.0)
    colors[:, 0] = 0.67 - t * 0.67
    colors[:, 1] = 1.0
    colors[:, 2] = 0.58
    return colors


def _distance_colors(xyz: np.ndarray) -> np.ndarray:
    colors = np.zeros((xyz.shape[0], 3), dtype=np.float32)
    distance = np.linalg.norm(xyz, axis=1)
    t = np.clip(distance / 18.0, 0.0, 1.0)
    colors[:, 0] = 0.7 - t * 0.7
    colors[:, 1] = 1.0
    colors[:, 2] = 0.58
    return colors


def parse_pointcloud2_msg(
    msg: Any,
    *,
    max_points: int = 30_000,
    max_range_m: float | None = 80.0,
    min_range_m: float = 0.05,
    downsample: bool = True,
    fallback_color_mode: str = "height",
) -> ParsedPointCloud | None:
    field_map = _field_map_from_msg(msg)
    return _parse_pointcloud2_binary(
        raw=bytes(msg.data),
        field_map=field_map,
        point_step=int(msg.point_step),
        is_bigendian=bool(msg.is_bigendian),
        frame_id=str(msg.header.frame_id or "map"),
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
) -> ParsedPointCloud | None:
    data = payload.get("data")
    point_step_raw = payload.get("point_step")
    if not isinstance(data, list):
        return None
    try:
        point_step = int(point_step_raw)
    except (TypeError, ValueError):
        return None
    if point_step <= 0:
        return None

    try:
        raw = bytes(int(value) & 0xFF for value in data)
    except (TypeError, ValueError):
        return None

    field_map = _field_map_from_yaml(payload)
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    frame_id = str((header or {}).get("frame_id") or "map")

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


def _parse_pointcloud2_binary(
    *,
    raw: bytes,
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
    required = ("x", "y", "z")
    if not all(name in field_map for name in required):
        return None

    total_points = len(raw) // point_step
    if total_points <= 0:
        return None

    stride = 1
    if downsample and total_points > max_points:
        stride = max(1, math.ceil(total_points / max(1, max_points)))

    little_endian = not is_bigendian
    x_offset, x_type = field_map["x"]
    y_offset, y_type = field_map["y"]
    z_offset, z_type = field_map["z"]

    rgb_mode: str | None = None
    rgb_offset = rgb_type = None
    if "rgb" in field_map:
        rgb_mode = "rgb"
        rgb_offset, rgb_type = field_map["rgb"]
    elif "rgba" in field_map:
        rgb_mode = "rgba"
        rgb_offset, rgb_type = field_map["rgba"]
    elif all(name in field_map for name in ("r", "g", "b")):
        rgb_mode = "separate"

    intensity_offset = intensity_type = None
    if "intensity" in field_map:
        intensity_offset, intensity_type = field_map["intensity"]

    xyz_rows: list[list[float]] = []
    rgb_rows: list[list[float]] = []
    intensity_rows: list[float] = []

    for index in range(0, total_points, stride):
        base = index * point_step

        x = _unpack_field(raw, offset=base + x_offset, datatype=x_type, little_endian=little_endian)
        y = _unpack_field(raw, offset=base + y_offset, datatype=y_type, little_endian=little_endian)
        z = _unpack_field(raw, offset=base + z_offset, datatype=z_type, little_endian=little_endian)

        if x is None or y is None or z is None:
            continue
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue

        distance = math.sqrt(x * x + y * y + z * z)
        if distance < min_range_m:
            continue
        if max_range_m is not None and distance > max_range_m:
            continue

        xyz_rows.append([float(x), float(y), float(z)])

        if rgb_mode == "rgb" and rgb_offset is not None and rgb_type is not None:
            packed = _unpack_field(
                raw,
                offset=base + rgb_offset,
                datatype=rgb_type,
                little_endian=little_endian,
            )
            decoded = _decode_rgb_packed(packed) if packed is not None else None
            rgb_rows.append(list(decoded) if decoded else [0.7, 0.7, 0.7])
        elif rgb_mode == "rgba" and rgb_offset is not None and rgb_type is not None:
            packed = _unpack_field(
                raw,
                offset=base + rgb_offset,
                datatype=rgb_type,
                little_endian=little_endian,
            )
            decoded = _decode_rgba_packed(packed) if packed is not None else None
            rgb_rows.append(list(decoded) if decoded else [0.7, 0.7, 0.7])
        elif rgb_mode == "separate":
            r_off, r_type = field_map["r"]
            g_off, g_type = field_map["g"]
            b_off, b_type = field_map["b"]
            r = _unpack_field(raw, offset=base + r_off, datatype=r_type, little_endian=little_endian)
            g = _unpack_field(raw, offset=base + g_off, datatype=g_type, little_endian=little_endian)
            b = _unpack_field(raw, offset=base + b_off, datatype=b_type, little_endian=little_endian)
            if r is None or g is None or b is None:
                rgb_rows.append([0.7, 0.7, 0.7])
            else:
                rgb_rows.append([float(r) / 255.0, float(g) / 255.0, float(b) / 255.0])

        if intensity_offset is not None and intensity_type is not None:
            value = _unpack_field(
                raw,
                offset=base + intensity_offset,
                datatype=intensity_type,
                little_endian=little_endian,
            )
            intensity_rows.append(float(value) if value is not None else 0.0)

        if len(xyz_rows) >= max_points:
            break

    if not xyz_rows:
        return None

    xyz = np.asarray(xyz_rows, dtype=np.float32)
    has_rgb = bool(rgb_rows) and len(rgb_rows) == xyz.shape[0]

    if has_rgb:
        rgb = np.asarray(rgb_rows, dtype=np.float32)
    else:
        if fallback_color_mode == "distance":
            rgb = _distance_colors(xyz)
        else:
            rgb = _height_distance_colors(xyz)

    intensity = None
    if intensity_rows and len(intensity_rows) == xyz.shape[0]:
        intensity = np.asarray(intensity_rows, dtype=np.float32)

    return ParsedPointCloud(
        xyz=xyz,
        rgb=rgb,
        has_rgb=has_rgb,
        frame_id=frame_id,
        point_count=int(xyz.shape[0]),
        intensity=intensity,
    )


def encode_xyz32(xyz: np.ndarray) -> bytes:
    return np.ascontiguousarray(xyz, dtype=np.float32).reshape((-1, 3)).tobytes()


def encode_xyzrgb32(xyz: np.ndarray, rgb: np.ndarray) -> bytes:
    positions = np.ascontiguousarray(xyz, dtype=np.float32).reshape((-1, 3)).tobytes()
    colors = np.clip(rgb, 0.0, 1.0)
    colors_u8 = (colors * 255.0).astype(np.uint8).reshape((-1, 3)).tobytes()
    return positions + colors_u8
