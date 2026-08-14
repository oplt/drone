"""Warehouse structure extraction — models."""

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

from .constants import _EXCLUDED_SOURCE_PREFIXES, _POINT_SUFFIXES, _SURFACE_SOURCE_PREFIXES


class StructureExtractionError(RuntimeError):
    pass

@dataclass(slots=True)
class StructureExtractionParams:
    """Tunables for the geometry heuristics + clearance gate."""

    voxel_m: float = 0.05
    grid_res_m: float = 0.10
    floor_margin_m: float = 0.15
    ceiling_max_m: float = 8.0
    min_aisle_width_m: float = 0.9
    min_rack_length_m: float = 0.6
    bin_pitch_m: float = 0.9
    shelf_min_spacing_m: float = 0.30
    max_shelf_levels: int = 6
    max_bins_per_rack_face: int = 24
    min_target_spacing_m: float = 0.75
    review_clearance_m: float = 0.10
    standoff_m: float = 1.2
    drone_radius_m: float = 0.35
    clearance_margin_m: float = 0.25
    max_points: int = 6_000_000
    min_surface_points: int = 0
    barcode_scan_expected: bool = False
    rack_template_version_id: int | None = None
    rack_template_bin_count: int | None = None
    rack_template_bay_width_m: float | None = None
    rack_template_shelf_levels_m: tuple[float, ...] = ()
    # Optional operator override for the aisle axis (degrees CCW from +X).
    axis_deg: float | None = None

    @property
    def required_clearance_m(self) -> float:
        return float(self.drone_radius_m) + float(self.clearance_margin_m)

    def sanitized(self) -> StructureExtractionParams:
        def _pos(value: float, default: float, *, minimum: float = 1e-4) -> float:
            try:
                v = float(value)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(v) or v < minimum:
                return default
            return v

        return StructureExtractionParams(
            voxel_m=_pos(self.voxel_m, 0.05),
            grid_res_m=_pos(self.grid_res_m, 0.10),
            floor_margin_m=_pos(self.floor_margin_m, 0.15, minimum=0.0),
            ceiling_max_m=_pos(self.ceiling_max_m, 8.0),
            min_aisle_width_m=_pos(self.min_aisle_width_m, 0.9),
            min_rack_length_m=_pos(self.min_rack_length_m, 0.6),
            bin_pitch_m=_pos(self.bin_pitch_m, 0.9),
            shelf_min_spacing_m=_pos(self.shelf_min_spacing_m, 0.30),
            max_shelf_levels=max(1, min(12, int(self.max_shelf_levels or 6))),
            max_bins_per_rack_face=max(1, min(80, int(self.max_bins_per_rack_face or 24))),
            min_target_spacing_m=_pos(self.min_target_spacing_m, 0.75),
            review_clearance_m=_pos(self.review_clearance_m, 0.10, minimum=0.0),
            standoff_m=_pos(self.standoff_m, 1.2),
            drone_radius_m=_pos(self.drone_radius_m, 0.35),
            clearance_margin_m=_pos(self.clearance_margin_m, 0.25, minimum=0.0),
            max_points=max(10_000, int(self.max_points or 6_000_000)),
            min_surface_points=max(0, int(self.min_surface_points or 0)),
            barcode_scan_expected=bool(self.barcode_scan_expected),
            rack_template_version_id=(
                None
                if self.rack_template_version_id is None
                else max(1, int(self.rack_template_version_id))
            ),
            rack_template_bin_count=(
                None
                if self.rack_template_bin_count is None
                else max(1, min(80, int(self.rack_template_bin_count)))
            ),
            rack_template_bay_width_m=(
                None
                if self.rack_template_bay_width_m is None
                else _pos(self.rack_template_bay_width_m, 1.0)
            ),
            rack_template_shelf_levels_m=_clean_template_levels(
                self.rack_template_shelf_levels_m
            ),
            axis_deg=(None if self.axis_deg is None else float(self.axis_deg)),
        )

@dataclass(slots=True)
class GeneratedTarget:
    aisle_code: str
    rack_code: str
    shelf_level: int
    bin_code: str
    target_point: dict[str, Any]
    shelf_normal: dict[str, Any]
    scan_pose: dict[str, Any]
    standoff_m: float
    priority: int
    clearance_status: str = "needs_review"
    clearance_m: float | None = None
    clearance_source: str = "point_cloud_kdtree"
    confidence: float = 0.5
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    template_metadata: dict[str, Any] = field(default_factory=dict)
    scanner_metadata: dict[str, Any] = field(default_factory=dict)
    path_validation: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None

@dataclass(slots=True)
class StructureResult:
    targets: list[GeneratedTarget] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    point_count: int = 0
    rejected_clearance: int = 0
    rejection_diagnostics: list[dict[str, Any]] = field(default_factory=list)

@dataclass(slots=True)
class _Band:
    lo: float
    hi: float

    @property
    def center(self) -> float:
        return 0.5 * (self.lo + self.hi)

    @property
    def width(self) -> float:
        return self.hi - self.lo

@dataclass(slots=True)
class _PlaneCluster:
    """A vertical rack-face plane in aisle-aligned UV coordinates."""

    v: float
    u_lo: float
    u_hi: float
    z_lo: float
    z_hi: float
    support_points: int
    residual_m: float
    source: str = "vertical_plane_edges"

    @property
    def span_u(self) -> float:
        return self.u_hi - self.u_lo

def _clean_template_levels(raw_levels: tuple[float, ...]) -> tuple[float, ...]:
    levels: list[float] = []
    for raw in raw_levels or ():
        try:
            level = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(level) and level >= 0.0:
            levels.append(level)
    return tuple(sorted(set(levels))[:12])
