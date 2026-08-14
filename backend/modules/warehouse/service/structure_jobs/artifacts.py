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

from .constants import (
    STRUCTURE_DEBUG_ASSET_TYPE,
    STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
    _HASH_CHUNK_SIZE_BYTES,
)
from .deps import resolve_chunk_storage, resolve_load_flight_manifest

def _write_summary_asset(
    client_flight_id: str, summary: dict[str, Any], lineage_checksum: str
) -> Path | None:
    """Persist the structure summary JSON next to the flight chunks."""
    try:
        flight_dir = resolve_chunk_storage().flight_dir(client_flight_id)
        flight_dir.mkdir(parents=True, exist_ok=True)
        path = flight_dir / f"structure_map-{lineage_checksum[:16]}.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return path
    except OSError:
        logger.warning("structure_extraction: failed to write summary asset", exc_info=True)
        return None

def _safe_debug_value(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)

def _structure_debug_chunk_id(lineage_checksum: str) -> str:
    return f"structure_debug-{lineage_checksum[:16]}"

def _write_debug_artifact(
    client_flight_id: str,
    *,
    payload: dict[str, Any],
    lineage_checksum: str,
) -> tuple[Path | None, str | None]:
    """Write downloadable JSON diagnostics next to persisted live-map chunks."""
    try:
        flight_dir = resolve_chunk_storage().flight_dir(client_flight_id)
        flight_dir.mkdir(parents=True, exist_ok=True)
        chunk_id = _structure_debug_chunk_id(lineage_checksum)
        encoded = json.dumps(payload, indent=2, sort_keys=True, default=_safe_debug_value)
        checksum = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        path = flight_dir / f"{chunk_id}-{checksum[:16]}.json"
        path.write_text(encoded, encoding="utf-8")
        stored = resolve_chunk_storage().resolve(
            flight_id=client_flight_id,
            chunk_id=chunk_id,
        )
        return path, stored.url if stored is not None else None
    except OSError:
        logger.warning("structure_extraction: failed to write debug artifact", exc_info=True)
        return None, None

def _source_layers_used(manifest_json: dict[str, Any] | None, inputs_json: list[dict[str, Any]] | None) -> list[str]:
    layers: set[str] = set()
    manifest_json = manifest_json if isinstance(manifest_json, dict) else {}
    for value in (manifest_json.get("chunk_counts") or {}).keys():
        if str(value).strip():
            layers.add(str(value))
    for row in inputs_json or []:
        if not isinstance(row, dict):
            continue
        source_quality = row.get("source_quality")
        if isinstance(source_quality, dict) and source_quality.get("source"):
            layers.add(str(source_quality["source"]))
    return sorted(layers)

def _debug_confidence_breakdown(summary: dict[str, Any]) -> dict[str, Any]:
    def collect(items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        values = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("confidence_breakdown"), dict):
                values.append(dict(item["confidence_breakdown"]))
        return values

    racks = summary.get("racks") if isinstance(summary, dict) else []
    aisles = summary.get("aisles") if isinstance(summary, dict) else []
    targets = summary.get("candidate_targets") if isinstance(summary, dict) else []
    return {
        "quality_confidence": (
            summary.get("quality", {}).get("confidence")
            if isinstance(summary.get("quality"), dict)
            else None
        ),
        "aisles": collect(aisles),
        "racks": collect(racks),
        "targets": collect(targets),
    }

def _shelf_histogram_peaks(summary: dict[str, Any]) -> list[dict[str, Any]]:
    peaks: list[dict[str, Any]] = []
    for rack in summary.get("racks") or []:
        if not isinstance(rack, dict):
            continue
        shelf = rack.get("shelf_detection")
        if not isinstance(shelf, dict):
            continue
        peaks.append(
            {
                "rack_code": rack.get("code"),
                "source": shelf.get("source"),
                "levels_m": list(shelf.get("levels_m") or []),
                "confidence_breakdown": dict(shelf.get("confidence_breakdown") or {}),
            }
        )
    return peaks

def _debug_payload(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    coordinate_frame_id: int | None,
    result: StructureResult | None,
    lineage_checksum: str | None,
    manifest_json: dict[str, Any] | None = None,
    inputs_json: list[dict[str, Any]] | None = None,
    failure_reason_codes: list[str] | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    summary = result.summary if result is not None else {}
    summary = summary if isinstance(summary, dict) else {}
    map_quality = summary.get("map_quality") if isinstance(summary.get("map_quality"), dict) else {}
    floor_z = summary.get("floor_z")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "warehouse_map_id": int(warehouse_map_id),
        "model_id": int(model_id),
        "client_flight_id": client_flight_id,
        "coordinate_frame_id": coordinate_frame_id,
        "artifact_set_checksum": lineage_checksum,
        "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
        "status": summary.get("status") or "failed",
        "failure_reason_codes": list(failure_reason_codes or []),
        "error_message": error_message,
        "quality": summary.get("quality"),
        "counts": summary.get("counts"),
        "target_counts": summary.get("target_counts"),
        "diagnostics": summary.get("diagnostics"),
        "landmark_frame_validation": (
            summary.get("landmark_frame_validation")
        ),
        "map_quality": summary.get("map_quality"),
        "clearance": summary.get("clearance"),
        "input_chunk_counts": dict(map_quality.get("chunk_counts") or {}),
        "source_layers_used": _source_layers_used(manifest_json, inputs_json),
        "floor_plane": {
            "frame_id": summary.get("frame_id"),
            "z_m": floor_z,
            "normal": [0.0, 0.0, 1.0] if floor_z is not None else None,
            "source": "floor_height_estimator" if floor_z is not None else None,
        },
        "detected_aisle_axis": {
            "axis_deg": summary.get("axis_deg"),
            "height_band_m": summary.get("height_band_m"),
            "graph": summary.get("aisle_graph"),
        },
        "rack_plane_clusters": list(summary.get("rack_plane_clusters") or []),
        "shelf_histogram_peaks": _shelf_histogram_peaks(summary),
        "rejected_target_diagnostics": list(summary.get("rejection_diagnostics") or []),
        "rejection_diagnostics": list(summary.get("rejection_diagnostics") or []),
        "confidence_breakdown": _debug_confidence_breakdown(summary),
        "candidate_preview": list(summary.get("candidate_targets") or [])[:50],
        "params": summary.get("params"),
        "manifest": manifest_json or {},
        "inputs": inputs_json or [],
    }

def _hash_input_file(path: Path) -> tuple[int, str]:
    """Hash a potentially large scan input without loading it into memory."""
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_SIZE_BYTES):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Scan input changed while lineage was captured: {path}")
    return after.st_size, digest.hexdigest()

def _scan_artifact_lineage(
    client_flight_id: str,
    *,
    model_id: int,
    coordinate_frame_id: int,
    extraction_params: dict[str, Any],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    flight_dir = resolve_chunk_storage().flight_dir(client_flight_id)
    inputs: list[dict[str, Any]] = []
    if flight_dir.exists():
        for path in sorted(item for item in flight_dir.rglob("*") if item.is_file()):
            if path.name.startswith(("structure_map", "structure_debug")):
                continue
            size_bytes, digest = _hash_input_file(path)
            input_row: dict[str, Any] = {
                "path": str(path.relative_to(flight_dir)),
                "size_bytes": size_bytes,
                "checksum_sha256": digest,
            }
            if not path.name.endswith(".meta.json"):
                chunk_id = path.stem.rsplit("-", 1)[0]
                sidecar = resolve_chunk_storage().load_chunk_metadata(
                    flight_id=client_flight_id,
                    chunk_id=chunk_id,
                )
                if isinstance(sidecar, dict):
                    input_row["source_quality"] = {
                        "source": sidecar.get("source"),
                        "point_count": sidecar.get("point_count"),
                        "has_rgb": bool(sidecar.get("has_rgb")),
                        "bbox_local_m": sidecar.get("bbox_local_m"),
                        "rack_face_id": sidecar.get("rack_face_id") or sidecar.get("face_id"),
                        "viewing_angle_deg": sidecar.get(
                            "viewing_angle_deg", sidecar.get("incidence_angle_deg")
                        ),
                    }
            inputs.append(input_row)
    manifest = resolve_load_flight_manifest()(client_flight_id)
    manifest_json = manifest.as_dict() if manifest is not None else {}
    lineage = {
        "client_flight_id": client_flight_id,
        "map_model_id": model_id,
        "coordinate_frame_id": coordinate_frame_id,
        "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
        "extraction_params": extraction_params,
        "manifest": manifest_json,
        "inputs": inputs,
    }
    checksum = hashlib.sha256(
        json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return checksum, manifest_json, inputs
