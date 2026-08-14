"""Warehouse structure extraction — geometry."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid
from backend.modules.warehouse.schemas import (
    WAREHOUSE_MAP_FRAME_ID,
    WarehouseLocalPoint,
    WarehouseShelfNormal,
)
from backend.modules.warehouse.service.coordinate_frames import transform_odom_points
from backend.modules.warehouse.service.inspection import compute_scan_pose
from backend.modules.warehouse.service.live_map_storage import warehouse_live_map_chunk_storage
from backend.modules.warehouse.service.occupancy_grid_parser import decode_occupancy_grid

logger = logging.getLogger(__name__)

def _dominant_axis_rad(xy: np.ndarray) -> float:
    """PCA major axis of the XY footprint (radians, CCW from +X)."""
    centered = xy - xy.mean(axis=0, keepdims=True)
    cov = np.cov(centered.T)
    if not np.all(np.isfinite(cov)):
        return 0.0
    eigvals, eigvecs = np.linalg.eigh(cov)
    major = eigvecs[:, int(np.argmax(eigvals))]
    return float(math.atan2(float(major[1]), float(major[0])))

def _rotation(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, s], [-s, c]], dtype=np.float64)
