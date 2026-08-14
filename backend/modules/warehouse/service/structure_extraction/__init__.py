"""Warehouse structure extraction — public package API."""

from __future__ import annotations

from .clearance import classify_clearance
from .deps import warehouse_live_map_chunk_storage
from .floor_ceiling import _detect_floor_z
from .geometry import _dominant_axis_rad
from .models import (
    GeneratedTarget,
    StructureExtractionError,
    StructureExtractionParams,
    StructureResult,
    _Band,
)
from .pipeline import extract_structure, extract_structure_from_flight
from .preprocessing import load_flight_cloud, load_flight_occupancy_grid, voxel_downsample
from .rack_detection import _density_bands, _extract_vertical_plane_rows
from .shelf_detection import _detect_shelf_levels
from .routing import _assign_astar_priority
from .target_generation import _emit_bay_targets

__all__ = [
    "GeneratedTarget",
    "StructureExtractionError",
    "StructureExtractionParams",
    "StructureResult",
    "_Band",
    "_assign_astar_priority",
    "_density_bands",
    "_detect_floor_z",
    "_detect_shelf_levels",
    "_dominant_axis_rad",
    "_emit_bay_targets",
    "_extract_vertical_plane_rows",
    "classify_clearance",
    "extract_structure",
    "extract_structure_from_flight",
    "load_flight_cloud",
    "load_flight_occupancy_grid",
    "voxel_downsample",
    "warehouse_live_map_chunk_storage",
]
