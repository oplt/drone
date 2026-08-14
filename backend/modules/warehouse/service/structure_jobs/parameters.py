"""Structure job module."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.infrastructure.cache.local import BoundedTTLCache
from backend.infrastructure.cache.redis import get_sync_redis_client, redis_available
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseCoordinateFrame,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    record_inspection_target_clearance_failure,
    record_low_confidence_candidate,
    record_structure_extraction_failure,
)
from backend.modules.warehouse.schemas import WarehouseLocalPose, WarehouseSensorAim
from backend.modules.warehouse.service.drift_guard import (
    transform_checksum,
    validate_localization_evidence,
)
from backend.modules.warehouse.service.gazebo_landmark_consistency import (
    LandmarkObservation,
    LandmarkSpec,
    evaluate_landmark_consistency,
)
from backend.modules.warehouse.service.layout import create_extracted_layout
from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest
from backend.modules.warehouse.service.live_map_readiness import (
    refresh_structure_input_readiness,
)
from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage,
)
from backend.modules.warehouse.service.occupancy_grid_parser import (
    occupancy_grid_from_ros_yaml,
)
from backend.modules.warehouse.service.scan_to_layout import (
    CandidateInput,
    extraction_confidence,
    persist_candidates,
)
from backend.modules.warehouse.service.structure_extraction import (
    StructureExtractionParams,
    StructureResult,
    extract_structure_from_flight,
)
from backend.observability.profiling import profile_stage

logger = logging.getLogger(__name__)


def params_from_payload(payload: dict[str, Any] | None) -> StructureExtractionParams:
    payload = payload or {}
    defaults = StructureExtractionParams(
        voxel_m=settings.warehouse_structure_voxel_m,
        grid_res_m=settings.warehouse_structure_grid_res_m,
        floor_margin_m=settings.warehouse_structure_floor_margin_m,
        ceiling_max_m=settings.warehouse_structure_ceiling_max_m,
        min_aisle_width_m=settings.warehouse_structure_min_aisle_width_m,
        min_rack_length_m=settings.warehouse_structure_min_rack_length_m,
        bin_pitch_m=settings.warehouse_structure_bin_pitch_m,
        shelf_min_spacing_m=settings.warehouse_structure_shelf_min_spacing_m,
        max_shelf_levels=settings.warehouse_structure_max_shelf_levels,
        max_bins_per_rack_face=settings.warehouse_structure_max_bins_per_rack_face,
        min_target_spacing_m=settings.warehouse_structure_min_target_spacing_m,
        review_clearance_m=settings.warehouse_structure_review_clearance_m,
        standoff_m=settings.warehouse_structure_standoff_m,
        drone_radius_m=settings.warehouse_structure_drone_radius_m,
        clearance_margin_m=settings.warehouse_structure_clearance_margin_m,
        max_points=settings.warehouse_structure_max_points,
        min_surface_points=settings.warehouse_structure_min_surface_points,
    )

    def override(name: str, current: float) -> float:
        value = payload.get(name)
        if value is None:
            return current
        try:
            return float(value)
        except (TypeError, ValueError):
            return current

    for name in (
        "voxel_m", "grid_res_m", "bin_pitch_m", "standoff_m", "drone_radius_m",
        "clearance_margin_m", "min_aisle_width_m", "shelf_min_spacing_m",
        "min_target_spacing_m", "review_clearance_m",
    ):
        setattr(defaults, name, override(name, getattr(defaults, name)))
    defaults.max_shelf_levels = int(override("max_shelf_levels", defaults.max_shelf_levels))
    defaults.max_bins_per_rack_face = int(
        override("max_bins_per_rack_face", defaults.max_bins_per_rack_face)
    )
    defaults.min_surface_points = int(override("min_surface_points", defaults.min_surface_points))
    for name in ("rack_template_bin_count", "rack_template_version_id"):
        value = payload.get(name)
        setattr(defaults, name, None if value is None else int(override(name, 1.0)))
    value = payload.get("rack_template_bay_width_m")
    defaults.rack_template_bay_width_m = None if value is None else override(
        "rack_template_bay_width_m", 1.0
    )
    raw_levels = payload.get("rack_template_shelf_levels_m")
    if isinstance(raw_levels, list):
        levels: list[float] = []
        for raw in raw_levels:
            try:
                levels.append(float(raw))
            except (TypeError, ValueError):
                continue
        defaults.rack_template_shelf_levels_m = tuple(levels)
    defaults.axis_deg = None if payload.get("axis_deg") is None else override("axis_deg", 0.0)
    return defaults.sanitized()
