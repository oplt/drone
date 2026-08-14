"""Warehouse structure extraction — clearance."""

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

def classify_clearance(
    clearance_m: float,
    *,
    strict_clearance_m: float,
    review_clearance_m: float,
    reliable_evidence: bool,
) -> str:
    if clearance_m >= strict_clearance_m:
        return "active" if reliable_evidence else "needs_review"
    if clearance_m >= review_clearance_m:
        return "needs_review"
    return "rejected"
