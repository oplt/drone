"""PointCloud2 parser — binary chunk encoders."""

from __future__ import annotations

import numpy as np


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


__all__ = ["encode_xyz32", "encode_xyzrgb32"]
