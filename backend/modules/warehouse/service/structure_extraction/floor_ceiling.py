"""Warehouse structure extraction — floor ceiling."""

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

def _detect_floor_z(z: np.ndarray, grid_res_m: float) -> float:
    """Floor height = densest z-bin within the lowest part of the cloud."""
    z_min = float(np.percentile(z, 0.5))
    z_max = float(np.percentile(z, 99.5))
    if z_max - z_min < grid_res_m:
        return z_min
    bins = max(8, math.ceil((z_max - z_min) / grid_res_m))
    hist, edges = np.histogram(z, bins=bins, range=(z_min, z_max))
    # Restrict floor search to the bottom third of the height range.
    cutoff = z_min + (z_max - z_min) * 0.34
    mask = edges[:-1] <= cutoff
    if not mask.any():
        return z_min
    region = np.where(mask, hist, 0)
    peak = int(np.argmax(region))
    return float((edges[peak] + edges[peak + 1]) * 0.5)
