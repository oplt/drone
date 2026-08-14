"""PointCloud2 parser — RGB decode and fallback coloring."""

from __future__ import annotations

import struct

import numpy as np


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
        rgb[:, 0] = ((packed >> 16) & 0xFF) / 255.0
        rgb[:, 1] = ((packed >> 8) & 0xFF) / 255.0
        rgb[:, 2] = (packed & 0xFF) / 255.0
    return rgb


__all__ = [
    "_decode_packed_rgb_array",
    "_decode_rgb_packed",
    "_decode_rgba_packed",
    "_distance_colors",
    "_height_distance_colors",
    "_normalise_rgb_array",
]
