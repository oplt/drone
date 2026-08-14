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
from backend.modules.warehouse.service.live_map_readiness import (
    refresh_structure_input_readiness,
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

from .deps import resolve_load_flight_manifest

from .constants import _PLACEHOLDER_FRAME_CHECKSUMS

def _validate_extraction_coordinate_frame(frame: WarehouseCoordinateFrame) -> None:
    checksum = str(frame.transform_checksum or "").strip().lower()
    if checksum in _PLACEHOLDER_FRAME_CHECKSUMS:
        raise RuntimeError(
            "Structure extraction requires a non-placeholder coordinate frame checksum"
        )
    if frame.transform_timestamp is None:
        raise RuntimeError("Locked coordinate frame is unsafe for extraction: missing timestamp")
    covariance = list(frame.covariance_json or [])
    if len(covariance) != 36:
        raise RuntimeError(
            "Structure extraction requires non-placeholder coordinate covariance"
        )
    try:
        position_variances = [float(covariance[index]) for index in (0, 7, 14)]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Structure extraction requires non-placeholder coordinate covariance"
        ) from exc
    if not all(math.isfinite(value) for value in position_variances) or all(
        abs(value) <= 1e-12 for value in position_variances
    ):
        raise RuntimeError(
            "Structure extraction requires non-placeholder coordinate covariance"
        )
    transform = frame.transform_json if isinstance(frame.transform_json, dict) else {}
    try:
        evidence = validate_localization_evidence(
            transform=transform,
            transform_timestamp=frame.transform_timestamp,
            max_age_s=float(frame.max_age_s),
            covariance=list(frame.covariance_json or []),
            confidence=float(frame.confidence or 0.0),
            min_confidence=float(settings.warehouse_structure_min_frame_confidence),
        )
    except ValueError as exc:
        raise RuntimeError(f"Locked coordinate frame is unsafe for extraction: {exc}") from exc
    if checksum != str(evidence["checksum_sha256"]).lower():
        raise RuntimeError("Structure extraction coordinate frame checksum mismatch")
    if checksum != transform_checksum(transform):
        raise RuntimeError("Structure extraction coordinate frame checksum mismatch")

def _pose_xyz(payload: dict[str, Any]) -> tuple[float, float, float] | None:
    if not isinstance(payload, dict):
        return None
    try:
        x = float(payload.get("x_m", payload.get("x")))
        y = float(payload.get("y_m", payload.get("y")))
        z = float(payload.get("z_m", payload.get("z", 0.0)))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x, y, z)):
        return None
    return x, y, z

def _landmark_observation_from_meta(meta: dict[str, Any]) -> dict[str, Any] | None:
    for key in (
        "marker_observation_odom",
        "marker_pose_odom",
        "observed_pose_odom",
        "last_observation_odom",
    ):
        value = meta.get(key)
        if isinstance(value, dict):
            return value
    return None

async def _validate_landmark_frame(
    db,
    *,
    warehouse_map_id: int,
    coordinate_frame: WarehouseCoordinateFrame,
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(WarehouseDockStation).where(
                WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                WarehouseDockStation.active.is_(True),
                WarehouseDockStation.marker_id.is_not(None),
            )
        )
    ).scalars().all()
    specs: list[LandmarkSpec] = []
    observations: list[LandmarkObservation] = []
    missing_observations: list[str] = []
    for dock in rows:
        name = str(dock.marker_id or dock.name or f"dock:{dock.id}")
        expected = _pose_xyz(dock.pose_local_json if isinstance(dock.pose_local_json, dict) else {})
        if expected is None:
            continue
        specs.append(
            LandmarkSpec(
                name=name,
                warehouse_x_m=expected[0],
                warehouse_y_m=expected[1],
                warehouse_z_m=expected[2],
            )
        )
        meta = dock.meta_data if isinstance(dock.meta_data, dict) else {}
        observed_payload = _landmark_observation_from_meta(meta)
        observed = _pose_xyz(observed_payload or {})
        if observed is None:
            missing_observations.append(name)
            continue
        observations.append(
            LandmarkObservation(name=name, x_m=observed[0], y_m=observed[1], z_m=observed[2])
        )

    if not specs:
        return {
            "status": "not_configured",
            "configured_landmarks": 0,
            "observed_landmarks": 0,
            "passed": None,
        }
    if not observations:
        return {
            "status": "missing_observations",
            "configured_landmarks": len(specs),
            "observed_landmarks": 0,
            "missing_observations": missing_observations,
            "passed": None,
        }
    evaluation = evaluate_landmark_consistency(
        landmarks=specs,
        observations=observations,
        map_to_odom=coordinate_frame.transform_json,
        tolerance_m=float(settings.warehouse_structure_landmark_tolerance_m),
    )
    evaluation["status"] = "passed" if evaluation.get("passed") else "failed"
    evaluation["configured_landmarks"] = len(specs)
    evaluation["observed_landmarks"] = len(observations)
    evaluation["missing_observations"] = missing_observations
    if not evaluation.get("passed"):
        raise RuntimeError(
            "Landmark-based warehouse frame validation failed: "
            + "; ".join(str(item) for item in evaluation.get("failures") or [])
        )
    return evaluation

def _manifest_point_total(manifest_json: dict[str, Any]) -> int:
    point_counts = manifest_json.get("point_counts")
    if isinstance(point_counts, dict):
        total = 0
        for value in point_counts.values():
            try:
                total += int(value or 0)
            except (TypeError, ValueError):
                continue
        return total
    return 0

def _surface_point_density(manifest_json: dict[str, Any]) -> float | None:
    source_quality = manifest_json.get("source_quality")
    if not isinstance(source_quality, dict):
        return None
    point_counts = manifest_json.get("point_counts")
    point_counts = point_counts if isinstance(point_counts, dict) else {}
    surface_sources = {
        "rgbd_colored",
        "rgbd_xyz_uncolored",
        "mid360_raw",
        "nvblox_color",
        "nvblox_tsdf",
    }
    total_points = 0
    total_area = 0.0
    for source, quality in source_quality.items():
        if str(source) not in surface_sources or not isinstance(quality, dict):
            continue
        try:
            area = float(quality.get("floor_area_m2") or 0.0)
            points = int(point_counts.get(source) or 0)
        except (TypeError, ValueError):
            continue
        if area <= 0.0 or points <= 0:
            continue
        total_area += area
        total_points += points
    if total_area <= 0.0:
        return None
    return float(total_points) / total_area

def _validate_manifest_coverage(client_flight_id: str, params: StructureExtractionParams) -> None:
    manifest = resolve_load_flight_manifest()(client_flight_id)
    if manifest is None:
        return
    manifest_json = manifest.as_dict()
    failures: list[str] = []
    threshold = int(params.min_surface_points or 0)
    total_points = _manifest_point_total(manifest_json)
    if threshold > 0 and total_points and total_points < threshold:
        failures.append(
            f"{total_points} manifest surface points, minimum={threshold}"
        )
    min_density = float(settings.warehouse_structure_min_surface_points_per_m2 or 0.0)
    density = _surface_point_density(manifest_json)
    if min_density > 0.0 and density is not None and density < min_density:
        failures.append(
            f"surface density {density:.2f} points/m2, minimum={min_density:.2f}"
        )
    chunk_counts = manifest_json.get("chunk_counts")
    chunk_counts = chunk_counts if isinstance(chunk_counts, dict) else {}
    occupancy_available = bool(manifest_json.get("occupancy_available")) or int(
        chunk_counts.get("nvblox_occupancy") or 0
    ) > 0
    esdf_available = bool(manifest_json.get("esdf_available")) or int(
        chunk_counts.get("nvblox_esdf") or 0
    ) > 0
    if bool(settings.warehouse_structure_require_occupancy_grid) and not occupancy_available:
        failures.append("occupancy grid present threshold failed")
    if (
        bool(settings.warehouse_structure_require_esdf_or_inflated_occupancy)
        and not (esdf_available or occupancy_available)
    ):
        failures.append("ESDF or inflated occupancy present threshold failed")
    max_tf_jumps = int(settings.warehouse_structure_max_tf_jump_count or 0)
    tf_jumps = int(manifest_json.get("tf_jump_back_count") or 0)
    if max_tf_jumps >= 0 and tf_jumps > max_tf_jumps:
        failures.append(f"TF jump count {tf_jumps}, maximum={max_tf_jumps}")
    if (
        bool(params.barcode_scan_expected)
        and bool(settings.warehouse_structure_require_rgb_when_barcode_expected)
        and not bool(manifest_json.get("rgbd_has_rgb"))
    ):
        failures.append("RGB-D/color present threshold failed for barcode/product scan")
    if failures:
        raise RuntimeError("Insufficient map coverage: " + "; ".join(failures) + ".")
