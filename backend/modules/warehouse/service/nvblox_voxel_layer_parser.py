from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ParsedVoxelLayer:
    xyz: np.ndarray
    rgb: np.ndarray | None
    has_rgb: bool
    point_count: int


def _finite_xyz_mask(xyz: np.ndarray) -> np.ndarray:
    return np.isfinite(xyz).all(axis=1)


def _subsample(
    xyz: np.ndarray,
    rgb: np.ndarray | None,
    *,
    max_points: int,
) -> tuple[np.ndarray, np.ndarray | None]:
    max_points = max(1, int(max_points or 1))
    if xyz.shape[0] <= max_points:
        return xyz, rgb
    stride = max(1, int(np.ceil(xyz.shape[0] / max_points)))
    xyz = np.ascontiguousarray(xyz[::stride][:max_points], dtype=np.float32)
    if rgb is not None:
        rgb = np.ascontiguousarray(rgb[::stride][:max_points], dtype=np.float32)
    return xyz, rgb


def _point_xyz(point: Any) -> tuple[float, float, float] | None:
    try:
        x = float(getattr(point, "x", 0.0))
        y = float(getattr(point, "y", 0.0))
        z = float(getattr(point, "z", 0.0))
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(x) and np.isfinite(y) and np.isfinite(z)):
        return None
    return x, y, z


def _color_rgb(color: Any) -> tuple[float, float, float] | None:
    try:
        r = float(getattr(color, "r", 0.0))
        g = float(getattr(color, "g", 0.0))
        b = float(getattr(color, "b", 0.0))
    except (TypeError, ValueError):
        return None
    if max(r, g, b) > 1.0:
        r, g, b = r / 255.0, g / 255.0, b / 255.0
    arr = np.asarray([r, g, b], dtype=np.float32)
    if not np.isfinite(arr).all():
        return None
    arr = np.clip(arr, 0.0, 1.0)
    return float(arr[0]), float(arr[1]), float(arr[2])


def parse_voxel_block_layer_msg(
    msg: Any,
    *,
    max_points: int = 20_000,
    require_color: bool = False,
) -> ParsedVoxelLayer | None:
    """Decode nvBlox VoxelBlockLayer plugin stream into XYZ plus optional RGB."""
    if bool(getattr(msg, "clear", False)):
        return None

    blocks = getattr(msg, "blocks", None) or []
    if not blocks:
        return None

    xyz_parts: list[tuple[float, float, float]] = []
    rgb_parts: list[tuple[float, float, float] | None] = []
    color_seen = False

    for block in blocks:
        centers = getattr(block, "centers", None) or []
        colors = getattr(block, "colors", None) or []
        for index, center in enumerate(centers):
            xyz = _point_xyz(center)
            if xyz is None:
                continue
            xyz_parts.append(xyz)
            rgb: tuple[float, float, float] | None = None
            if index < len(colors):
                rgb = _color_rgb(colors[index])
                if rgb is not None:
                    color_seen = True
            rgb_parts.append(rgb)

    if not xyz_parts:
        return None

    xyz = np.ascontiguousarray(np.asarray(xyz_parts, dtype=np.float32).reshape((-1, 3)))
    mask = _finite_xyz_mask(xyz)
    if not bool(mask.any()):
        return None
    if not bool(mask.all()):
        xyz = xyz[mask]
        rgb_parts = [rgb for rgb, keep in zip(rgb_parts, mask.tolist()) if keep]

    rgb_array: np.ndarray | None = None
    if color_seen and all(rgb is not None for rgb in rgb_parts) and len(rgb_parts) == xyz.shape[0]:
        rgb_array = np.ascontiguousarray(np.asarray(rgb_parts, dtype=np.float32).reshape((-1, 3)))
    elif require_color:
        return None

    xyz, rgb_array = _subsample(xyz, rgb_array, max_points=max_points)
    if xyz.size <= 0:
        return None

    return ParsedVoxelLayer(
        xyz=xyz,
        rgb=rgb_array,
        has_rgb=rgb_array is not None,
        point_count=int(xyz.shape[0]),
    )
