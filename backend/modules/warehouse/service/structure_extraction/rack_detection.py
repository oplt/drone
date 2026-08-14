"""Warehouse structure extraction — rack detection."""

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

from . import deps
from .confidence import _confidence_mean, _score_from_residual
from .geometry import _rotation
from .models import StructureExtractionParams, _Band, _PlaneCluster

def _density_bands(
    coord: np.ndarray,
    *,
    res: float,
    occupied: bool,
    min_width: float,
    occ_threshold: float,
) -> list[_Band]:
    """Return contiguous bands along ``coord`` that are occupied/free.

    A 1-D histogram is thresholded; ``scipy.ndimage.label`` groups contiguous
    runs. ``occupied=True`` keeps high-density runs (rack rows); ``occupied=False``
    keeps low-density runs (aisles).
    """
    lo = float(coord.min())
    hi = float(coord.max())
    if hi - lo < res:
        return []
    nbins = max(4, math.ceil((hi - lo) / res))
    hist, edges = np.histogram(coord, bins=nbins, range=(lo, hi))
    peak = float(hist.max()) if hist.size else 0.0
    if peak <= 0:
        return []
    norm = hist.astype(np.float64) / peak
    selector = norm >= occ_threshold if occupied else norm < occ_threshold
    labels, count = ndimage.label(selector)
    bands: list[_Band] = []
    for label_id in range(1, count + 1):
        idx = np.flatnonzero(labels == label_id)
        band = _Band(lo=float(edges[idx[0]]), hi=float(edges[idx[-1] + 1]))
        if band.width >= min_width:
            bands.append(band)
    return bands

def _extract_vertical_plane_rows(
    *,
    u_all: np.ndarray,
    v_all: np.ndarray,
    z_all: np.ndarray,
    params: StructureExtractionParams,
) -> tuple[list[_Band], list[_PlaneCluster], bool]:
    """Detect rack rows from vertical face plane pairs.

    The old extractor treated dense cross-axis bands as rack rows. This keeps
    that as a fallback, but the primary signal is now the pair of boundary
    planes around each occupied rack row. That gives every row explicit face
    plane evidence and a residual instead of a bare 1-D density band.
    """
    density_rows = deps.resolve("_density_bands")(
        v_all,
        res=params.grid_res_m,
        occupied=True,
        min_width=params.grid_res_m * 2,
        occ_threshold=0.18,
    )
    plane_rows: list[_Band] = []
    planes: list[_PlaneCluster] = []
    for row in density_rows:
        in_row = (v_all >= row.lo) & (v_all <= row.hi)
        if int(in_row.sum()) < 30:
            continue
        row_v = v_all[in_row].astype(np.float64)
        row_u = u_all[in_row].astype(np.float64)
        row_z = z_all[in_row].astype(np.float64)
        lo_plane_v = float(np.percentile(row_v, 8.0))
        hi_plane_v = float(np.percentile(row_v, 92.0))
        if hi_plane_v - lo_plane_v < params.grid_res_m:
            continue
        row_planes: list[_PlaneCluster] = []
        for plane_v in (lo_plane_v, hi_plane_v):
            distances = np.abs(row_v - plane_v)
            near = distances <= max(params.grid_res_m * 1.5, 0.12)
            if not near.any():
                near = distances <= float(np.percentile(distances, 20.0))
            if int(near.sum()) < 12:
                continue
            row_planes.append(
                _PlaneCluster(
                    v=plane_v,
                    u_lo=float(np.percentile(row_u[near], 2.0)),
                    u_hi=float(np.percentile(row_u[near], 98.0)),
                    z_lo=float(np.percentile(row_z[near], 2.0)),
                    z_hi=float(np.percentile(row_z[near], 98.0)),
                    support_points=int(near.sum()),
                    residual_m=float(np.median(distances[near])),
                )
            )
        if len(row_planes) < 2:
            continue
        planes.extend(row_planes)
        plane_rows.append(_Band(lo=min(p.v for p in row_planes), hi=max(p.v for p in row_planes)))

    if plane_rows:
        return plane_rows, planes, False
    return density_rows, [], True

def _plane_for_face(face: dict[str, Any], planes: list[_PlaneCluster]) -> _PlaneCluster | None:
    if not planes:
        return None
    face_v = float(face["face_v"])
    return min(planes, key=lambda plane: abs(float(plane.v) - face_v))

def _upright_bays(
    *,
    u_row: np.ndarray,
    z_row: np.ndarray,
    params: StructureExtractionParams,
) -> list[_Band]:
    """Detect rack bays from repeated vertical upright/support concentrations."""
    if u_row.size < 30:
        return []
    u_min = float(u_row.min())
    u_max = float(u_row.max())
    span = u_max - u_min
    if span < params.min_rack_length_m:
        return []
    nbins = max(6, math.ceil(span / max(params.grid_res_m, 0.05)))
    hist, edges = np.histogram(u_row, bins=nbins, range=(u_min, u_max))
    if hist.max() <= 0:
        return []
    smooth = ndimage.gaussian_filter1d(hist.astype(np.float64), sigma=1.0)
    threshold = max(float(smooth.mean() + smooth.std() * 0.35), float(smooth.max()) * 0.35)
    peak_idx: list[int] = []
    for index in range(1, len(smooth) - 1):
        if (
            smooth[index] >= threshold
            and smooth[index] >= smooth[index - 1]
            and smooth[index] >= smooth[index + 1]
        ):
            peak_idx.append(index)
    if len(peak_idx) < 2:
        return []
    upright_u = [float((edges[index] + edges[index + 1]) * 0.5) for index in peak_idx]
    filtered: list[float] = []
    for value in upright_u:
        if not filtered or abs(value - filtered[-1]) >= max(params.min_rack_length_m * 0.4, 0.25):
            filtered.append(value)
    if len(filtered) < 2:
        return []
    bays: list[_Band] = []
    for left, right in zip(filtered, filtered[1:], strict=False):
        if right - left >= params.min_rack_length_m:
            bays.append(_Band(lo=left, hi=right))
    if not bays:
        return []
    # Avoid a common failure mode where dense shelf clutter creates too many tiny bays.
    if len(bays) > params.max_bins_per_rack_face:
        return []
    return bays

def _template_bays(
    *,
    u_min: float,
    u_max: float,
    bay_width_m: float,
    min_rack_length_m: float,
) -> list[_Band]:
    span = max(0.0, float(u_max) - float(u_min))
    width = max(float(min_rack_length_m), float(bay_width_m))
    if span <= 0.0 or width <= 0.0:
        return []
    count = max(1, round(span / width))
    actual = span / count
    return [
        _Band(lo=float(u_min) + index * actual, hi=float(u_min) + (index + 1) * actual)
        for index in range(count)
        if actual >= min_rack_length_m
    ]

def _rack_face_plane_summary(
    *,
    u_row: np.ndarray,
    v_row: np.ndarray,
    z_row: np.ndarray,
    bay: _Band,
    face: dict[str, Any],
    uv_to_world,
    plane_cluster: _PlaneCluster | None = None,
    fallback: bool = False,
) -> dict[str, Any]:
    in_bay = (u_row >= bay.lo) & (u_row <= bay.hi)
    candidates = v_row[in_bay]
    z_candidates = z_row[in_bay]
    face_v = float(plane_cluster.v) if plane_cluster is not None else float(face["face_v"])
    if plane_cluster is not None:
        residual = float(plane_cluster.residual_m)
        points = int(plane_cluster.support_points)
    elif candidates.size == 0:
        residual = None
        points = 0
    else:
        distances = np.abs(candidates.astype(np.float64) - face_v)
        near = distances <= max(0.20, float(bay.width) * 0.05)
        if not near.any():
            near = distances <= float(np.percentile(distances, 25.0))
        residual = float(np.median(distances[near])) if near.any() else float(np.median(distances))
        points = int(near.sum()) if near.any() else int(candidates.size)
    x0, y0 = uv_to_world(bay.lo, face_v)
    x1, y1 = uv_to_world(bay.hi, face_v)
    return {
        "aisle_code": str(face.get("aisle_code") or ""),
        "plane_kind": "vertical_rack_face",
        "line_world": [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)],
        "residual_rms_m": None if residual is None else round(residual, 4),
        "support_points": points,
        "z_min": None if z_candidates.size == 0 else round(float(z_candidates.min()), 3),
        "z_max": None if z_candidates.size == 0 else round(float(z_candidates.max()), 3),
        "source": "density_fallback" if fallback else "vertical_plane_extraction",
        "confidence": round(_score_from_residual(residual, good_m=0.04, bad_m=0.25), 3),
    }

def _template_fit_metrics(
    *,
    bay: _Band,
    shelf_levels: list[float],
    params: StructureExtractionParams,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {"applied": False}
    scores: list[float] = []
    if params.rack_template_bay_width_m is not None:
        width = float(params.rack_template_bay_width_m)
        residual = abs(float(bay.width) - width)
        metrics.update(
            {
                "applied": True,
                "bay_width_m": round(width, 3),
                "bay_width_residual_m": round(residual, 4),
            }
        )
        scores.append(_score_from_residual(residual, good_m=0.03, bad_m=max(0.25, width * 0.25)))
    if params.rack_template_shelf_levels_m:
        expected = list(params.rack_template_shelf_levels_m)
        paired = zip(sorted(shelf_levels), expected, strict=False)
        residuals = [abs(float(left) - float(right)) for left, right in paired]
        residual = max(residuals) if residuals else None
        metrics.update(
            {
                "applied": True,
                "shelf_levels_m": [round(float(value), 3) for value in expected],
                "shelf_level_residual_m": None if residual is None else round(residual, 4),
            }
        )
        scores.append(_score_from_residual(residual, good_m=0.03, bad_m=0.20))
    if params.rack_template_bin_count is not None:
        metrics.update(
            {
                "applied": True,
                "bin_count": int(params.rack_template_bin_count),
            }
        )
        scores.append(1.0)
    metrics["confidence"] = _confidence_mean(scores) if scores else 0.5
    return metrics
