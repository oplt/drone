"""Warehouse structure extraction — confidence."""

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

from .models import StructureExtractionParams

def _score_from_residual(residual_m: float | None, *, good_m: float, bad_m: float) -> float:
    if residual_m is None or not math.isfinite(float(residual_m)):
        return 0.5
    value = float(residual_m)
    if value <= good_m:
        return 1.0
    if value >= bad_m:
        return 0.0
    return max(0.0, min(1.0, 1.0 - ((value - good_m) / (bad_m - good_m))))

def _confidence_mean(values: list[float]) -> float:
    if not values:
        return 0.5
    clean = [max(0.0, min(1.0, float(value))) for value in values if math.isfinite(float(value))]
    return round(sum(clean) / len(clean), 3) if clean else 0.5

def _rack_confidence_breakdown(
    *,
    points: int,
    face_planes: list[dict[str, Any]],
    template_fit: dict[str, Any],
    shelf_confidence: dict[str, float] | None = None,
    fallback: bool = False,
) -> dict[str, float]:
    point_score = max(0.0, min(1.0, float(points) / 500.0))
    plane_scores = [
        float(face.get("confidence"))
        for face in face_planes
        if isinstance(face.get("confidence"), (int, float))
    ]
    plane_score = _confidence_mean(plane_scores)
    template_score = float(template_fit.get("confidence") or 0.5)
    shelf_score = (
        float(shelf_confidence.get("geometry"))
        if isinstance(shelf_confidence, dict)
        and isinstance(shelf_confidence.get("geometry"), (int, float))
        else 0.5
    )
    fallback_score = 0.25 if fallback else 1.0
    return {
        "point_support": round(point_score, 3),
        "rack_face_plane": round(plane_score, 3),
        "shelf_planes": round(max(0.0, min(1.0, shelf_score)), 3),
        "template_fit": round(max(0.0, min(1.0, template_score)), 3),
        "fallback_extractor": fallback_score,
        "geometry": _confidence_mean(
            [point_score, plane_score, template_score, shelf_score, fallback_score]
        ),
    }

def _target_confidence_breakdown(
    *,
    clearance_status: str,
    clearance_source: str,
    face_plane: dict[str, Any] | None,
    template_fit: dict[str, Any] | None,
) -> dict[str, float]:
    clearance_score = (
        1.0
        if clearance_status == "active"
        else 0.65
        if clearance_status == "needs_review"
        else 0.2
    )
    evidence_score = 1.0 if clearance_source == "occupancy_grid" else 0.55
    plane_score = (
        float(face_plane.get("confidence"))
        if isinstance(face_plane, dict) and isinstance(face_plane.get("confidence"), (int, float))
        else 0.5
    )
    template_score = (
        float(template_fit.get("confidence"))
        if isinstance(template_fit, dict)
        and isinstance(template_fit.get("confidence"), (int, float))
        else 0.5
    )
    return {
        "clearance": round(clearance_score, 3),
        "clearance_evidence": round(evidence_score, 3),
        "rack_face_plane": round(max(0.0, min(1.0, plane_score)), 3),
        "template_fit": round(max(0.0, min(1.0, template_score)), 3),
    }
