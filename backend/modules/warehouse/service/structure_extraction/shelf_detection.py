"""Warehouse structure extraction — shelf detection."""

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

from .confidence import _confidence_mean, _score_from_residual
from .models import StructureExtractionParams

def _shelf_confidence_breakdown(
    *,
    levels: list[float],
    z_points: np.ndarray,
    params: StructureExtractionParams,
) -> dict[str, float]:
    if not levels:
        return {"horizontal_plane_support": 0.0, "pitch_prior": 0.0, "geometry": 0.0}
    support_scores: list[float] = []
    for level in levels:
        near = np.abs(z_points.astype(np.float64) - float(level)) <= max(params.grid_res_m, 0.08)
        support_scores.append(max(0.0, min(1.0, float(near.sum()) / 50.0)))
    pitch_score = 1.0
    if len(levels) > 1:
        gaps = np.diff(sorted(float(level) for level in levels))
        expected = max(params.shelf_min_spacing_m, 1e-6)
        residual = float(np.median(np.abs(gaps - expected)))
        pitch_score = _score_from_residual(residual, good_m=0.08, bad_m=max(0.35, expected))
    support = _confidence_mean(support_scores)
    return {
        "horizontal_plane_support": support,
        "pitch_prior": round(pitch_score, 3),
        "geometry": _confidence_mean([support, pitch_score]),
    }

def _detect_shelf_levels(
    z: np.ndarray,
    *,
    spacing: float,
    res: float,
    max_levels: int,
) -> list[float]:
    """Z-histogram peaks = horizontal shelf beams (regular spacing prior)."""
    z_lo = float(z.min())
    z_hi = float(z.max())
    if z_hi - z_lo < spacing:
        return [0.5 * (z_lo + z_hi)]
    nbins = max(4, math.ceil((z_hi - z_lo) / res))
    hist, edges = np.histogram(z, bins=nbins, range=(z_lo, z_hi))
    if hist.max() <= 0:
        return [0.5 * (z_lo + z_hi)]
    norm = hist.astype(np.float64) / float(hist.max())
    # Minimum index separation between distinct shelves.
    min_sep = max(1, round(spacing / res))
    candidates = [i for i in range(len(norm)) if norm[i] >= 0.45]
    levels: list[float] = []
    last = -min_sep
    for i in candidates:
        if i - last < min_sep:
            # Keep the denser of the two adjacent peaks.
            if levels and norm[i] > norm[last]:
                levels[-1] = float((edges[i] + edges[i + 1]) * 0.5)
                last = i
            continue
        levels.append(float((edges[i] + edges[i + 1]) * 0.5))
        last = i
    if not levels:
        return [0.5 * (z_lo + z_hi)]
    if len(levels) <= max_levels:
        return levels
    # Keep the strongest separated shelf bands instead of every small noisy z peak.
    ranked = sorted(
        levels,
        key=lambda level: hist[min(len(hist) - 1, max(0, int((level - z_lo) / max(res, 1e-6))))],
        reverse=True,
    )[:max_levels]
    return sorted(ranked)
