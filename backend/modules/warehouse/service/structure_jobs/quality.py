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

from .failure_codes import _quality_failure_reason_codes

def _has_reliable_clearance_evidence(summary: dict[str, Any]) -> bool:
    diagnostics = summary.get("diagnostics") if isinstance(summary, dict) else {}
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    map_quality = summary.get("map_quality") if isinstance(summary, dict) else {}
    map_quality = map_quality if isinstance(map_quality, dict) else {}
    chunk_counts = map_quality.get("chunk_counts")
    chunk_counts = chunk_counts if isinstance(chunk_counts, dict) else {}
    clearance = summary.get("clearance") if isinstance(summary, dict) else {}
    clearance = clearance if isinstance(clearance, dict) else {}
    return (
        bool(diagnostics.get("occupancy_available"))
        or bool(diagnostics.get("esdf_available"))
        or int(chunk_counts.get("nvblox_occupancy") or 0) > 0
        or int(chunk_counts.get("nvblox_esdf") or 0) > 0
        or str(clearance.get("source") or "") == "occupancy_grid"
    )

def _refresh_target_counts(result: StructureResult) -> None:
    target_counts = {
        "candidate": len(result.targets),
        "active": sum(target.clearance_status == "active" for target in result.targets),
        "needs_review": sum(target.clearance_status == "needs_review" for target in result.targets),
        "rejected": sum(target.clearance_status == "rejected" for target in result.targets),
    }
    result.summary["target_counts"] = target_counts
    counts = result.summary.setdefault("counts", {})
    if isinstance(counts, dict):
        counts["targets"] = len(result.targets)
        counts["active_targets"] = target_counts["active"]
        counts["review_targets"] = target_counts["needs_review"]
        counts["candidate_targets"] = target_counts["candidate"]
        counts["rejected_clearance"] = result.rejected_clearance
    summaries = []
    for target in result.targets:
        summaries.append(
            {
                "candidate_id": (
                    f"{target.rack_code}:{target.aisle_code}:{target.bin_code}:"
                    f"L{target.shelf_level}"
                ),
                "aisle_code": target.aisle_code,
                "rack_code": target.rack_code,
                "shelf_level": target.shelf_level,
                "bin_code": target.bin_code,
                "status": target.clearance_status,
                "clearance_m": (
                    round(target.clearance_m, 3) if target.clearance_m is not None else None
                ),
                "clearance_source": target.clearance_source,
                "confidence": round(float(getattr(target, "confidence", 0.5)), 3),
                "confidence_breakdown": dict(getattr(target, "confidence_breakdown", {}) or {}),
                "target_point": dict(target.target_point),
                "scan_pose": dict(target.scan_pose),
            }
        )
    result.summary["candidate_targets"] = summaries
    result.summary["active_targets"] = [
        item for item in summaries if item["status"] == "active"
    ]
    result.summary["review_targets"] = [
        item for item in summaries if item["status"] == "needs_review"
    ]
    result.summary["rejected_targets"] = [
        item for item in summaries if item["status"] == "rejected"
    ]
    result.summary["status"] = "ready" if target_counts["active"] > 0 else "degraded"
    result.summary["coordinate_setup_status"] = (
        "active" if target_counts["active"] > 0 else "draft"
    )
    result.summary["manual_review_required"] = (
        target_counts["needs_review"] > 0 or target_counts["active"] == 0
    )

def _force_review_without_clearance_evidence(result: StructureResult) -> None:
    if not bool(settings.warehouse_structure_require_clearance_evidence):
        return
    if _has_reliable_clearance_evidence(result.summary):
        return
    changed = False
    for target in result.targets:
        if target.clearance_status == "active":
            target.clearance_status = "needs_review"
            target.clearance_source = target.clearance_source or "missing_clearance_evidence"
            changed = True
    if not changed:
        return
    _refresh_target_counts(result)
    warnings = result.summary.setdefault("warnings", [])
    if isinstance(warnings, list):
        warnings.append(
            "Reliable occupancy/ESDF clearance evidence is missing; active targets require review."
        )
    result.summary["clearance_evidence_required"] = True

def _record_result_observability(result: StructureResult, *, confidence_threshold: float = 0.75) -> None:
    for target in result.targets:
        if float(getattr(target, "confidence", 0.0) or 0.0) < confidence_threshold:
            record_low_confidence_candidate(source=str(getattr(target, "clearance_source", "unknown")))
        if getattr(target, "clearance_status", None) == "rejected":
            record_inspection_target_clearance_failure(
                source=str(getattr(target, "clearance_source", "unknown"))
            )
    for diagnostic in result.rejection_diagnostics:
        if isinstance(diagnostic, dict):
            record_inspection_target_clearance_failure(
                source=str(diagnostic.get("clearance_source") or "diagnostic")
            )

def _attach_quality_gate(result: StructureResult) -> None:
    """Mark suspicious auto-detect output as draft-only instead of trusted ready data."""
    ensure_structure_quality_summary(result.summary, rejected_clearance=result.rejected_clearance)

def ensure_structure_quality_summary(
    summary: dict[str, Any],
    *,
    rejected_clearance: int | None = None,
) -> dict[str, Any]:
    """Backfill quality metadata for new and legacy structure summaries."""
    existing = summary.get("quality") if isinstance(summary, dict) else None
    if isinstance(existing, dict) and existing.get("status"):
        existing.setdefault("failure_reason_codes", list(existing.get("reasons") or []))
        return summary

    counts = summary.get("counts") if isinstance(summary, dict) else {}
    counts = counts if isinstance(counts, dict) else {}
    map_quality = summary.get("map_quality") if isinstance(summary, dict) else {}
    map_quality = map_quality if isinstance(map_quality, dict) else {}
    clearance = summary.get("clearance") if isinstance(summary, dict) else {}
    clearance = clearance if isinstance(clearance, dict) else {}
    landmark_validation = (
        summary.get("landmark_frame_validation") if isinstance(summary, dict) else {}
    )
    landmark_validation = landmark_validation if isinstance(landmark_validation, dict) else {}

    candidate_count = int(counts.get("candidate_targets") or counts.get("targets") or 0)
    # New summaries carry an explicit active-target count produced by the
    # clearance classifier. Legacy summaries only have the total ``targets``
    # field (a candidate count), so the active tally is derived from the gate
    # status below instead of trusting that raw number.
    has_explicit_active_count = "active_targets" in counts
    target_count = int(
        counts.get("active_targets") if has_explicit_active_count else counts.get("targets") or 0
    )
    rack_count = int(counts.get("racks") or 0)
    aisle_count = int(counts.get("aisles") or 0)
    rejected = int(counts.get("rejected_clearance") or rejected_clearance or 0)
    if candidate_count <= 0:
        candidate_count = target_count + rejected
    rejection_ratio = float(rejected) / float(candidate_count) if candidate_count > 0 else 0.0
    targets_per_rack = (
        float(candidate_count) / float(rack_count) if rack_count > 0 else float(candidate_count)
    )
    chunk_counts = (
        map_quality.get("chunk_counts") if isinstance(map_quality.get("chunk_counts"), dict) else {}
    )
    point_counts = (
        map_quality.get("point_counts") if isinstance(map_quality.get("point_counts"), dict) else {}
    )
    source_quality = (
        map_quality.get("source_quality")
        if isinstance(map_quality.get("source_quality"), dict)
        else {}
    )
    clearance_source = str(clearance.get("source") or "unknown")

    reasons: list[str] = []
    if candidate_count <= 0 or rack_count <= 0 or aisle_count <= 0:
        reasons.append("insufficient_detected_structure")
    if rack_count > 0 and targets_per_rack > 24.0:
        reasons.append("too_many_targets_per_rack")
    if candidate_count >= 20 and rejection_ratio >= 0.40:
        reasons.append("clearance_rejection_ratio_high")
    diagnostics = summary.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    occupancy_available = (
        bool(diagnostics.get("occupancy_available"))
        or int(chunk_counts.get("nvblox_occupancy") or 0) > 0
    )
    esdf_available = (
        bool(diagnostics.get("esdf_available")) or int(chunk_counts.get("nvblox_esdf") or 0) > 0
    )
    if not occupancy_available:
        reasons.append("missing_occupancy_grid")
    if 0 < int(point_counts.get("nvblox_esdf") or 0) < 5_000:
        reasons.append("weak_esdf")
    esdf_quality = source_quality.get("nvblox_esdf") if isinstance(source_quality, dict) else None
    if isinstance(esdf_quality, dict):
        try:
            esdf_ppm2 = float(esdf_quality.get("points_per_m2") or 0.0)
        except (TypeError, ValueError):
            esdf_ppm2 = 0.0
        if 0.0 < esdf_ppm2 < 15.0:
            reasons.append("weak_esdf")
    if bool(map_quality.get("tf_degraded")) or int(map_quality.get("tf_jump_back_count") or 0) >= 3:
        reasons.append("tf_instability")
    rack_face_coverage = map_quality.get("rack_face_coverage")
    rack_face_coverage = rack_face_coverage if isinstance(rack_face_coverage, dict) else {}
    if int(rack_face_coverage.get("uncovered_face_count") or 0) > 0:
        reasons.append("rack_face_coverage_incomplete")
    landmark_status = str(landmark_validation.get("status") or "")
    if landmark_status == "failed":
        reasons.append("landmark_frame_validation_failed")
    elif landmark_status == "missing_observations":
        reasons.append("missing_landmark_observations")
    missing_topics = map_quality.get("missing_topics")
    if not esdf_available and (
        not isinstance(missing_topics, list)
        or any("esdf" in str(topic) for topic in missing_topics)
    ):
        reasons.append("missing_esdf_topic")

    unique_reasons = sorted(set(reasons))
    confidence = 1.0
    if "missing_occupancy_grid" in unique_reasons:
        confidence -= 0.35
    if "clearance_rejection_ratio_high" in unique_reasons:
        confidence -= 0.25
    if "too_many_targets_per_rack" in unique_reasons:
        confidence -= 0.25
    if "weak_esdf" in unique_reasons:
        confidence -= 0.10
    if "tf_instability" in unique_reasons:
        confidence -= 0.20
    if "rack_face_coverage_incomplete" in unique_reasons:
        confidence -= 0.15
    if "landmark_frame_validation_failed" in unique_reasons:
        confidence -= 0.40
    if "missing_landmark_observations" in unique_reasons:
        confidence -= 0.10
    if "insufficient_detected_structure" in unique_reasons:
        confidence -= 0.50
    confidence = max(0.0, min(1.0, confidence))
    status = "needs_review" if unique_reasons else "ready"

    if has_explicit_active_count:
        active_target_count = target_count
    else:
        # Legacy summaries cannot distinguish active from candidate targets, so
        # only trust them as active when the gate is clean.
        active_target_count = target_count if status == "ready" else 0

    summary["quality"] = {
        "status": status,
        "confidence": round(confidence, 3),
        "reasons": unique_reasons,
        "failure_reason_codes": unique_reasons,
        "target_count": target_count,
        "active_target_count": active_target_count,
        "candidate_count": candidate_count,
        "rejected_clearance": rejected,
        "rejection_ratio": round(rejection_ratio, 3),
        "targets_per_rack": round(targets_per_rack, 3) if rack_count > 0 else None,
        "clearance_source": clearance_source,
        "tf_degraded": bool(map_quality.get("tf_degraded")),
        "tf_jump_back_count": int(map_quality.get("tf_jump_back_count") or 0),
        "rack_face_coverage": rack_face_coverage,
        "coverage_repair": (
            map_quality.get("coverage_repair")
            if isinstance(map_quality.get("coverage_repair"), dict)
            else {}
        ),
    }
    return summary
