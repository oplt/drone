from __future__ import annotations

import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

_POINTFIELD_DATATYPE_SIZE: dict[int, int] = {
    1: 1,  # INT8
    2: 1,  # UINT8
    3: 2,  # INT16
    4: 2,  # UINT16
    5: 4,  # INT32
    6: 4,  # UINT32
    7: 4,  # FLOAT32
    8: 8,  # FLOAT64
}

_POINTFIELD_NUMPY_DTYPE: dict[int, str] = {
    1: "i1",
    2: "u1",
    3: "i2",
    4: "u2",
    5: "i4",
    6: "u4",
    7: "f4",
    8: "f8",
}

COLOR_FIELD_NAMES = frozenset({"rgb", "rgba", "bgr", "bgra"})


@dataclass(frozen=True)
class ParsedPointCloud:
    xyz: np.ndarray
    rgb: np.ndarray | None
    has_rgb: bool
    frame_id: str
    point_count: int
    intensity: np.ndarray | None = None
    fields: tuple[str, ...] = ()


def detect_color_fields(fields: Any) -> dict[str, Any] | None:
    """Describe a supported PointCloud2 color layout without assuming color exists."""
    names = {
        str(getattr(field, "name", field.get("name") if isinstance(field, Mapping) else ""))
        .strip()
        .lower()
        for field in (fields or ())
    }
    packed = next((name for name in ("rgb", "rgba", "bgr", "bgra") if name in names), None)
    if packed is not None:
        return {"mode": "packed", "field": packed}
    if {"r", "g", "b"}.issubset(names):
        return {"mode": "separate", "fields": ("r", "g", "b")}
    return None


def _safe_int(value: Any, *, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _normalise_frame_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:128] or None


def _unpack_field(
    raw: bytes | bytearray | memoryview,
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

    # Common nvblox/PCL rgba convention: 0xRRGGBBAA.
    r = ((packed >> 24) & 0xFF) / 255.0
    g = ((packed >> 16) & 0xFF) / 255.0
    b = ((packed >> 8) & 0xFF) / 255.0
    return (r, g, b)


def _field_map_from_msg(msg: Any) -> dict[str, tuple[int, int]]:
    fields: dict[str, tuple[int, int]] = {}
    for field in getattr(msg, "fields", ()) or ():
        name = str(getattr(field, "name", "") or "").strip().lower()
        if not name:
            continue
        offset = _safe_int(getattr(field, "offset", None))
        datatype = _safe_int(getattr(field, "datatype", None))
        if offset is None or datatype is None:
            continue
        fields[name] = (offset, datatype)
    return fields


def _field_map_from_yaml(payload: Mapping[str, Any]) -> dict[str, tuple[int, int]]:
    fields: dict[str, tuple[int, int]] = {}
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list):
        return fields
    for field in raw_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip().lower()
        if not name:
            continue
        offset = _safe_int(field.get("offset"))
        datatype = _safe_int(field.get("datatype"))
        if offset is None or datatype is None:
            continue
        fields[name] = (offset, datatype)
    return fields


def _field_is_valid(
    field_map: Mapping[str, tuple[int, int]],
    name: str,
    *,
    point_step: int,
) -> bool:
    item = field_map.get(name)
    if item is None:
        return False
    offset, datatype = item
    size = _POINTFIELD_DATATYPE_SIZE.get(datatype)
    return size is not None and offset >= 0 and offset + size <= point_step


def _field_dtype(datatype: int, *, little_endian: bool) -> np.dtype | None:
    code = _POINTFIELD_NUMPY_DTYPE.get(datatype)
    if code is None:
        return None
    dtype = np.dtype(code)
    if dtype.itemsize > 1:
        dtype = dtype.newbyteorder("<" if little_endian else ">")
    return dtype


def _read_field_array(
    raw: bytes | bytearray | memoryview,
    *,
    offset: int,
    datatype: int,
    point_step: int,
    total_points: int,
    little_endian: bool,
    indices: np.ndarray | slice | None = None,
) -> np.ndarray | None:
    dtype = _field_dtype(datatype, little_endian=little_endian)
    if dtype is None:
        return None
    try:
        values = np.ndarray(
            shape=(total_points,),
            dtype=dtype,
            buffer=raw,
            offset=offset,
            strides=(point_step,),
        )
    except (TypeError, ValueError, BufferError):
        return None
    if indices is not None:
        values = values[indices]
    return values


def _height_distance_colors(xyz: np.ndarray) -> np.ndarray:
    colors = np.zeros((xyz.shape[0], 3), dtype=np.float32)
    if xyz.shape[0] <= 0:
        return colors
    z = xyz[:, 2]
    finite_z = z[np.isfinite(z)]
    if finite_z.size == 0:
        colors[:, 1] = 1.0
        colors[:, 2] = 0.58
        return colors
    min_z = float(finite_z.min())
    max_z = float(finite_z.max())
    span = max(0.001, max_z - min_z)
    t = np.clip((z - min_z) / span, 0.0, 1.0)
    colors[:, 0] = 0.67 - t * 0.67
    colors[:, 1] = 1.0
    colors[:, 2] = 0.58
    return colors


def _distance_colors(xyz: np.ndarray) -> np.ndarray:
    colors = np.zeros((xyz.shape[0], 3), dtype=np.float32)
    if xyz.shape[0] <= 0:
        return colors
    distance = np.linalg.norm(xyz, axis=1)
    t = np.clip(distance / 18.0, 0.0, 1.0)
    colors[:, 0] = 0.7 - t * 0.7
    colors[:, 1] = 1.0
    colors[:, 2] = 0.58
    return colors


def _normalise_rgb_array(values: np.ndarray) -> np.ndarray:
    rgb = np.asarray(values, dtype=np.float32).reshape((-1, 3))
    finite = np.isfinite(rgb)
    if not finite.all():
        rgb = np.where(finite, rgb, 0.7)
    # Some PointCloud2 publishers expose separate r/g/b as 0..255; others use 0..1.
    if rgb.size and float(np.nanmax(rgb)) > 1.0:
        rgb = rgb / 255.0
    return np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)


def _decode_packed_rgb_array(
    values: np.ndarray,
    *,
    mode: str,
    datatype: int,
) -> np.ndarray | None:
    try:
        if datatype == 7:
            packed = np.asarray(values, dtype=np.float32).view(np.uint32)
        else:
            packed = np.asarray(values, dtype=np.uint32)
    except (TypeError, ValueError):
        return None

    rgb = np.empty((packed.shape[0], 3), dtype=np.float32)
    if mode in {"bgr", "bgra"}:
        rgb[:, 0] = (packed & 0xFF) / 255.0
        rgb[:, 1] = ((packed >> 8) & 0xFF) / 255.0
        rgb[:, 2] = ((packed >> 16) & 0xFF) / 255.0
    else:
        # PCL/ROS commonly stores both rgb and rgba as 0xAARRGGBB.
        rgb[:, 0] = ((packed >> 16) & 0xFF) / 255.0
        rgb[:, 1] = ((packed >> 8) & 0xFF) / 255.0
        rgb[:, 2] = (packed & 0xFF) / 255.0
    return rgb


def parse_pointcloud2_msg(
    msg: Any,
    *,
    max_points: int = 30_000,
    max_range_m: float | None = 80.0,
    min_range_m: float = 0.05,
    downsample: bool = True,
    fallback_color_mode: str = "height",
) -> ParsedPointCloud | None:
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
) -> ParsedPointCloud | None:
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
    # Fast path for the common ROS PointCloud2 layout: x/y/z are numeric fields.
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


def encode_xyz32(xyz: np.ndarray) -> bytes:
    arr = np.ascontiguousarray(xyz, dtype=np.float32).reshape((-1, 3))
    if arr.size == 0:
        return b""
    return arr.tobytes()


def encode_xyzrgb32(xyz: np.ndarray, rgb: np.ndarray) -> bytes:
    positions_arr = np.ascontiguousarray(xyz, dtype=np.float32).reshape((-1, 3))
    colors_arr = np.ascontiguousarray(rgb, dtype=np.float32).reshape((-1, 3))
    if positions_arr.shape[0] != colors_arr.shape[0]:
        raise ValueError("xyz and rgb arrays must contain the same number of points.")
    positions = positions_arr.tobytes()
    colors = np.clip(colors_arr, 0.0, 1.0)
    colors_u8 = (colors * 255.0).astype(np.uint8).reshape((-1, 3)).tobytes()
    return positions + colors_u8
