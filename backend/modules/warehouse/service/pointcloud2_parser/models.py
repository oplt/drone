"""PointCloud2 parser — parsed cloud model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ParsedPointCloud:
    xyz: np.ndarray
    rgb: np.ndarray | None
    has_rgb: bool
    frame_id: str
    point_count: int
    intensity: np.ndarray | None = None
    fields: tuple[str, ...] = ()


__all__ = ["ParsedPointCloud"]
