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


def _subsample(
    xyz: np.ndarray,
    rgb: np.ndarray | None,
    *,
    max_points: int,
) -> tuple[np.ndarray, np.ndarray | None]:
    if xyz.shape[0] <= max_points:
        return xyz, rgb
    stride = max(1, int(np.ceil(xyz.shape[0] / max_points)))
    xyz = xyz[::stride][:max_points]
    if rgb is not None:
        rgb = rgb[::stride][:max_points]
    return xyz, rgb


def parse_voxel_block_layer_msg(
    msg: Any,
    *,
    max_points: int = 20_000,
    require_color: bool = False,
) -> ParsedVoxelLayer | None:
    """Decode nvBlox VoxelBlockLayer plugin stream into XYZ (+ optional RGB)."""
    if bool(getattr(msg, "clear", False)):
        return None

    blocks = getattr(msg, "blocks", None) or []
    if not blocks:
        return None

    xyz_parts: list[list[float]] = []
    rgb_parts: list[list[float]] = []
    has_rgb = False

    for block in blocks:
        centers = getattr(block, "centers", None) or []
        colors = getattr(block, "colors", None) or []
        for index, center in enumerate(centers):
            xyz_parts.append(
                [
                    float(getattr(center, "x", 0.0)),
                    float(getattr(center, "y", 0.0)),
                    float(getattr(center, "z", 0.0)),
                ]
            )
            if index < len(colors):
                color = colors[index]
                rgb_parts.append(
                    [
                        float(getattr(color, "r", 0.0)),
                        float(getattr(color, "g", 0.0)),
                        float(getattr(color, "b", 0.0)),
                    ]
                )
                has_rgb = True

    if not xyz_parts:
        return None

    xyz = np.asarray(xyz_parts, dtype=np.float32)
    rgb_array: np.ndarray | None = None
    if has_rgb and len(rgb_parts) == xyz.shape[0]:
        rgb_array = np.clip(np.asarray(rgb_parts, dtype=np.float32), 0.0, 1.0)
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
