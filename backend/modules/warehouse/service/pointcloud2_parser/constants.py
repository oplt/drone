"""PointCloud2 parser — field datatype constants."""

from __future__ import annotations

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

__all__ = [
    "COLOR_FIELD_NAMES",
    "_POINTFIELD_DATATYPE_SIZE",
    "_POINTFIELD_NUMPY_DTYPE",
]
