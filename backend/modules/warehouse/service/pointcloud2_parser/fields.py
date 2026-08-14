"""PointCloud2 parser — field layout detection and binary reads."""

from __future__ import annotations

import struct
from collections.abc import Mapping
from typing import Any

import numpy as np

from .constants import _POINTFIELD_DATATYPE_SIZE, _POINTFIELD_NUMPY_DTYPE
from .coercion import _safe_int


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


__all__ = [
    "_field_is_valid",
    "_field_map_from_msg",
    "_field_map_from_yaml",
    "_read_field_array",
    "_unpack_field",
    "detect_color_fields",
]
