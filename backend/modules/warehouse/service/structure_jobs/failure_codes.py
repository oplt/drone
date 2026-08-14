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


def _failure_reason_codes_from_message(message: str) -> list[str]:
    text = str(message or "").lower()
    reason_map = (
        ("locked warehouse coordinate frame", "missing_locked_coordinate_frame"),
        ("localization is required", "missing_locked_coordinate_frame"),
        ("non-placeholder coordinate frame checksum", "placeholder_coordinate_frame_checksum"),
        ("coordinate frame checksum mismatch", "coordinate_frame_checksum_mismatch"),
        ("localization confidence", "localization_confidence_low"),
        ("missing timestamp", "missing_coordinate_frame_evidence"),
        ("landmark-based warehouse frame validation failed", "landmark_frame_validation_failed"),
        ("non-placeholder coordinate covariance", "placeholder_coordinate_frame_covariance"),
        ("insufficient map coverage", "insufficient_map_coverage"),
        ("no surface point-cloud chunks", "missing_surface_pointcloud"),
        ("all merged points were non-finite", "invalid_pointcloud"),
        ("cloud too small", "insufficient_pointcloud"),
        ("no vertical structure", "insufficient_detected_structure"),
        ("no rack rows", "insufficient_detected_structure"),
        ("no usable rack structure", "insufficient_detected_structure"),
        ("worker", "worker_unavailable"),
    )
    codes = [code for needle, code in reason_map if needle in text]
    return sorted(set(codes or ["structure_extraction_failed"]))

def _record_extraction_failure_metrics(reason_codes: list[str]) -> None:
    for reason in sorted(set(reason_codes or ["structure_extraction_failed"])):
        record_structure_extraction_failure(reason=reason)

def _quality_failure_reason_codes(summary: dict[str, Any]) -> list[str]:
    quality = summary.get("quality") if isinstance(summary, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    reasons = [str(reason) for reason in quality.get("reasons") or []]
    status = str(quality.get("status") or summary.get("status") or "")
    if status == "ready" and not reasons:
        return []
    if reasons:
        return sorted(set(reasons))
    if status in {"failed", "degraded", "needs_review"}:
        return ["structure_quality_not_ready"]
    return []
