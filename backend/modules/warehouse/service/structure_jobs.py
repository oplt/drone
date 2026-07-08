"""Async orchestration for warehouse structure extraction.

Bridges the pure-geometry :mod:`structure_extraction` module to the database:
runs the heavy CPU work in a worker thread, then (idempotently) replaces the
auto-generated ``WarehouseScanTarget`` rows for a model and writes a
``STRUCTURE_MAP`` asset the frontend can use to draw aisle/rack overlays.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from datetime import UTC, datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseCoordinateFrame,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseModel,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.schemas import WarehouseLocalPose, WarehouseSensorAim
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
from backend.modules.warehouse.service.gazebo_landmark_consistency import (
    LandmarkObservation,
    LandmarkSpec,
    evaluate_landmark_consistency,
)
from backend.modules.warehouse.service.drift_guard import (
    transform_checksum,
    validate_localization_evidence,
)
from backend.modules.warehouse.service.structure_extraction import (
    StructureExtractionParams,
    StructureResult,
    extract_structure_from_flight,
)
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    record_inspection_target_clearance_failure,
    record_low_confidence_candidate,
    record_structure_extraction_failure,
)

logger = logging.getLogger(__name__)
STRUCTURE_EXTRACTION_ALGORITHM_VERSION = "warehouse-structure-v1"
_HASH_CHUNK_SIZE_BYTES = 1024 * 1024

STRUCTURE_ASSET_TYPE = "STRUCTURE_MAP"
STRUCTURE_DEBUG_ASSET_TYPE = "STRUCTURE_DEBUG"
EXTRACTION_TASK_NAME = "warehouse_mapping.extract_structure"
_PLACEHOLDER_FRAME_CHECKSUMS = {"", "0" * 64}

# In-process extraction job state keyed by warehouse_map_id. Survives API
# polling between enqueue (persist_capture or UI) and Celery completion.
_EXTRACTION_STATE: dict[int, dict[str, Any]] = {}
_EXTRACTION_CELERY_PROBE_AT: dict[int, float] = {}
_WORKER_READY_CACHE: tuple[float, bool, str | None] | None = None


def record_extraction_queued(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    task_id: str | None = None,
    source: str = "api",
) -> dict[str, Any]:
    state = {
        "status": "queued",
        "warehouse_map_id": int(warehouse_map_id),
        "model_id": int(model_id),
        "client_flight_id": str(client_flight_id),
        "task_id": task_id,
        "source": source,
        "requested_at": datetime.now(UTC).isoformat(),
        "error_message": None,
    }
    _EXTRACTION_STATE[int(warehouse_map_id)] = state
    return state


def record_extraction_running(*, warehouse_map_id: int) -> None:
    state = _EXTRACTION_STATE.setdefault(int(warehouse_map_id), {})
    state["status"] = "running"
    state["started_at"] = datetime.now(UTC).isoformat()


def record_extraction_ready(*, warehouse_map_id: int, target_count: int) -> None:
    _EXTRACTION_STATE.pop(int(warehouse_map_id), None)


def record_extraction_failed(
    *,
    warehouse_map_id: int,
    error_message: str,
    failure_reason_codes: list[str] | None = None,
    debug_artifact_url: str | None = None,
) -> None:
    state = _EXTRACTION_STATE.setdefault(int(warehouse_map_id), {})
    state["status"] = "failed"
    state["error_message"] = str(error_message or "Structure extraction failed.")[:2000]
    state["failure_reason_codes"] = list(failure_reason_codes or [])
    state["debug_artifact_url"] = debug_artifact_url
    state["finished_at"] = datetime.now(UTC).isoformat()


def _celery_probe_interval_s() -> float:
    from backend.core.config.runtime import settings

    return max(
        0.5,
        float(getattr(settings, "structure_extraction_celery_probe_interval_s", 3.0)),
    )


def get_extraction_state(warehouse_map_id: int) -> dict[str, Any] | None:
    state = _EXTRACTION_STATE.get(int(warehouse_map_id))
    if state is None:
        return None
    task_id = state.get("task_id")
    if not task_id:
        return dict(state)
    raw_status = str(state.get("status") or "queued")
    now = time.monotonic()
    last_probe = _EXTRACTION_CELERY_PROBE_AT.get(int(warehouse_map_id), 0.0)
    if raw_status not in {"queued", "running"} or (now - last_probe) < _celery_probe_interval_s():
        return dict(state)
    try:
        from celery.result import AsyncResult

        from backend.entrypoints.workers.celery_app import celery_app

        result = AsyncResult(str(task_id), app=celery_app)
        celery_state = str(result.state or "").upper()
        if celery_state in {"PENDING", "RECEIVED", "RETRY"}:
            state = {**state, "status": "queued"}
        elif celery_state == "STARTED":
            state = {**state, "status": "running"}
        elif celery_state == "SUCCESS":
            state = {**state, "status": "ready"}
        elif celery_state in {"FAILURE", "REVOKED"}:
            state = {
                **state,
                "status": "failed",
                "error_message": str(result.result or state.get("error_message") or "failed"),
            }
        _EXTRACTION_CELERY_PROBE_AT[int(warehouse_map_id)] = now
    except Exception:
        logger.debug("structure_extraction_status_probe_failed", exc_info=True)
    _EXTRACTION_STATE[int(warehouse_map_id)] = state
    return dict(state)


def warehouse_mapping_worker_ready(*, force: bool = False) -> tuple[bool, str | None]:
    """Return whether a warehouse-mapping worker has the extract task registered."""
    global _WORKER_READY_CACHE
    from backend.core.config.runtime import settings

    ttl = max(1.0, float(getattr(settings, "warehouse_mapping_worker_probe_cache_ttl_s", 20.0)))
    now = time.monotonic()
    if not force and _WORKER_READY_CACHE is not None:
        cached_at, ready, detail = _WORKER_READY_CACHE
        if (now - cached_at) < ttl:
            return ready, detail

    def _finish(ready: bool, detail: str | None) -> tuple[bool, str | None]:
        global _WORKER_READY_CACHE
        _WORKER_READY_CACHE = (now, ready, detail)
        return ready, detail

    try:
        from backend.entrypoints.workers.celery_app import celery_app

        if EXTRACTION_TASK_NAME not in celery_app.tasks:
            return _finish(
                False,
                "Structure extraction task is not registered in this API process. "
                "Restart the dev stack with `make warehouse`.",
            )
        inspect = celery_app.control.inspect(timeout=0.75)
        queues_by_worker = inspect.active_queues() or {}
        registered_by_worker = inspect.registered() or {}
    except Exception:
        logger.debug("warehouse_mapping_worker_probe_failed", exc_info=True)
        return _finish(False, "Could not reach Celery workers.")
    if not queues_by_worker:
        return _finish(
            False,
            "No Celery workers are running. Start `warehouse_mapping_worker` via `make warehouse`.",
        )

    queue_name = settings.celery_warehouse_mapping_queue
    workers_on_queue: list[str] = []
    workers_missing_task: list[str] = []
    for worker_name, queues in queues_by_worker.items():
        if not any(queue.get("name") == queue_name for queue in queues or []):
            continue
        workers_on_queue.append(worker_name)
        worker_tasks = set(registered_by_worker.get(worker_name) or [])
        if EXTRACTION_TASK_NAME not in worker_tasks:
            workers_missing_task.append(worker_name)

    if not workers_on_queue:
        return _finish(
            False,
            f"No worker is consuming the `{queue_name}` queue. "
            "Start `warehouse_mapping_worker` via `make warehouse`.",
        )
    if workers_missing_task:
        return _finish(
            False,
            "Warehouse mapping worker is running but has not loaded "
            f"`{EXTRACTION_TASK_NAME}`. Restart with `make warehouse` to pick up new code.",
        )
    return _finish(True, None)


def _write_summary_asset(
    client_flight_id: str, summary: dict[str, Any], lineage_checksum: str
) -> Path | None:
    """Persist the structure summary JSON next to the flight chunks."""
    try:
        flight_dir = warehouse_live_map_chunk_storage.flight_dir(client_flight_id)
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
        flight_dir = warehouse_live_map_chunk_storage.flight_dir(client_flight_id)
        flight_dir.mkdir(parents=True, exist_ok=True)
        chunk_id = _structure_debug_chunk_id(lineage_checksum)
        encoded = json.dumps(payload, indent=2, sort_keys=True, default=_safe_debug_value)
        checksum = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        path = flight_dir / f"{chunk_id}-{checksum[:16]}.json"
        path.write_text(encoded, encoding="utf-8")
        stored = warehouse_live_map_chunk_storage.resolve(
            flight_id=client_flight_id,
            chunk_id=chunk_id,
        )
        return path, stored.url if stored is not None else None
    except OSError:
        logger.warning("structure_extraction: failed to write debug artifact", exc_info=True)
        return None, None


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
    manifest = load_flight_manifest(client_flight_id)
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
    flight_dir = warehouse_live_map_chunk_storage.flight_dir(client_flight_id)
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
                sidecar = warehouse_live_map_chunk_storage.load_chunk_metadata(
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
    manifest = load_flight_manifest(client_flight_id)
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


async def _persist_result(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    result: StructureResult,
    coordinate_frame_id: int,
) -> dict[str, Any]:
    quality = result.summary.get("quality") if isinstance(result.summary, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    quality_status = str(quality.get("status") or "ready")
    active_target_count = sum(target.clearance_status == "active" for target in result.targets)
    review_target_count = sum(
        target.clearance_status == "needs_review" for target in result.targets
    )
    rejected_target_count = sum(target.clearance_status == "rejected" for target in result.targets)
    extraction_params = dict(result.summary.get("params") or {})
    lineage_checksum, manifest_json, inputs_json = await asyncio.to_thread(
        _scan_artifact_lineage,
        client_flight_id,
        model_id=int(model_id),
        coordinate_frame_id=int(coordinate_frame_id),
        extraction_params=extraction_params,
    )
    failure_reason_codes = _quality_failure_reason_codes(result.summary)
    summary_path = await asyncio.to_thread(
        _write_summary_asset, client_flight_id, result.summary, lineage_checksum
    )
    debug_payload = _debug_payload(
        warehouse_map_id=warehouse_map_id,
        model_id=model_id,
        client_flight_id=client_flight_id,
        coordinate_frame_id=coordinate_frame_id,
        result=result,
        lineage_checksum=lineage_checksum,
        manifest_json=manifest_json,
        inputs_json=inputs_json,
        failure_reason_codes=failure_reason_codes,
    )
    debug_path, debug_url = await asyncio.to_thread(
        _write_debug_artifact,
        client_flight_id,
        payload=debug_payload,
        lineage_checksum=lineage_checksum,
    )

    async with Session() as db:
        try:
            model = await db.get(WarehouseModel, int(model_id))
            if model is None:
                raise RuntimeError(f"Warehouse model {model_id} was not found")
            model.coordinate_frame_id = int(coordinate_frame_id)
            warehouse_map = await db.get(WarehouseMap, int(warehouse_map_id))
            if warehouse_map is None:
                raise RuntimeError(f"Warehouse map {warehouse_map_id} was not found")
            rig_scope = (
                WarehouseSensorRig.org_id == warehouse_map.org_id
                if warehouse_map.org_id is not None
                else and_(
                    WarehouseSensorRig.org_id.is_(None),
                    WarehouseSensorRig.owner_id == warehouse_map.owner_id,
                )
            )
            sensor_rig = (
                await db.execute(
                    select(WarehouseSensorRig)
                    .where(
                        WarehouseSensorRig.active.is_(True),
                        WarehouseSensorRig.calibration_status == "valid",
                        WarehouseSensorRig.calibration_hash.is_not(None),
                        rig_scope,
                    )
                    .order_by(WarehouseSensorRig.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            artifact_set = (
                await db.execute(
                    select(WarehouseScanArtifactSet).where(
                        WarehouseScanArtifactSet.checksum_sha256 == lineage_checksum
                    )
                )
            ).scalar_one_or_none()
            if artifact_set is None:
                artifact_set = WarehouseScanArtifactSet(
                    warehouse_map_id=int(warehouse_map_id),
                    map_model_id=int(model_id),
                    coordinate_frame_id=int(coordinate_frame_id),
                    sensor_rig_id=int(sensor_rig.id) if sensor_rig is not None else None,
                    calibration_hash=(
                        sensor_rig.calibration_hash if sensor_rig is not None else None
                    ),
                    client_flight_id=client_flight_id,
                    checksum_sha256=lineage_checksum,
                    manifest_json=manifest_json,
                    inputs_json=inputs_json,
                    extraction_params_json=extraction_params,
                    algorithm_version=STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                )
                db.add(artifact_set)
                await db.flush()
            layout, bin_ids, published = await create_extracted_layout(
                db,
                warehouse_map_id=int(warehouse_map_id),
                coordinate_frame_id=int(coordinate_frame_id),
                map_model_id=int(model_id),
                artifact_set_id=int(artifact_set.id),
                input_checksum=lineage_checksum,
                algorithm_version=STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                targets=result.targets,
            )
            await persist_candidates(
                db,
                warehouse_map_id=int(warehouse_map_id),
                layout_version_id=int(layout.id),
                candidates=[
                    CandidateInput(
                        entity_kind="bin",
                        identity_key=(
                            f"{target.aisle_code}/{target.rack_code}/"
                            f"{target.shelf_level}/{target.bin_code}"
                        ),
                        geometry={"target_point": target.target_point},
                        confidence=extraction_confidence(target),
                    )
                    for target in result.targets
                ],
            )
            # Idempotent re-run: drop the previous auto-generated targets for this
            # model (identified by reference_model_id) while leaving operator-made
            # targets (reference_model_id NULL or other models) untouched.
            await db.execute(
                delete(WarehouseScanTarget).where(
                    WarehouseScanTarget.warehouse_map_id == int(warehouse_map_id),
                    WarehouseScanTarget.reference_model_id == int(model_id),
                    WarehouseScanTarget.provenance_status == "auto",
                )
            )

            for tgt in result.targets:
                scan_pose = WarehouseLocalPose.model_validate(tgt.scan_pose).model_dump()
                scan_pose["_clearance_status"] = tgt.clearance_status
                scan_pose["_clearance_m"] = tgt.clearance_m
                scan_pose["_clearance_source"] = tgt.clearance_source
                db.add(
                    WarehouseScanTarget(
                        warehouse_map_id=int(warehouse_map_id),
                        reference_model_id=int(model_id),
                        coordinate_frame_id=int(coordinate_frame_id),
                        layout_version_id=int(layout.id),
                        bin_id=bin_ids[
                            (
                                str(tgt.aisle_code),
                                str(tgt.rack_code),
                                int(tgt.shelf_level),
                                str(tgt.bin_code),
                            )
                        ],
                        aisle_code=tgt.aisle_code,
                        rack_code=tgt.rack_code,
                        shelf_level=tgt.shelf_level,
                        bin_code=tgt.bin_code,
                        target_point_local_json=tgt.target_point,
                        scan_pose_local_json=scan_pose,
                        sensor_aim_json=WarehouseSensorAim(
                            aim_point_local_json=tgt.target_point,
                            orientation=scan_pose["orientation"],
                        ).model_dump(),
                        shelf_normal_local_json=tgt.shelf_normal,
                        scanner_metadata_json=dict(tgt.scanner_metadata or {}),
                        path_validation_json=dict(tgt.path_validation or {}),
                        failure_reason=tgt.failure_reason,
                        standoff_m=float(tgt.standoff_m),
                        priority=int(tgt.priority),
                        active=(
                            published
                            and tgt.clearance_status == "active"
                            and tgt.failure_reason is None
                        ),
                        provenance_status="auto",
                    )
                )

            db.add(
                WarehouseAsset(
                    model_id=int(model_id),
                    coordinate_frame_id=int(coordinate_frame_id),
                    frame_id="warehouse_map",
                    type=STRUCTURE_ASSET_TYPE,
                    url=str(summary_path) if summary_path else f"memory://structure/{model_id}",
                    checksum=hashlib.sha256(
                        json.dumps(result.summary, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    meta_data={
                        "warehouse_map_id": int(warehouse_map_id),
                        "coordinate_frame_id": int(coordinate_frame_id),
                        "artifact_set_id": int(artifact_set.id),
                        "input_checksum": lineage_checksum,
                        "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                        "layout_version_id": int(layout.id),
                        "layout_published": published,
                        "client_flight_id": client_flight_id,
                        "generated_at": datetime.now(UTC).isoformat(),
                        "summary": result.summary,
                        "target_count": len(result.targets),
                        "active_target_count": active_target_count,
                        "review_target_count": review_target_count,
                        "rejected_target_count": rejected_target_count,
                        "coordinate_setup_status": (
                            "active" if active_target_count > 0 else "draft"
                        ),
                        "manual_review_required": quality_status != "ready"
                        or review_target_count > 0,
                        "quality_status": quality_status,
                        "quality_reasons": list(quality.get("reasons") or []),
                        "failure_reason_codes": failure_reason_codes,
                        "confidence": quality.get("confidence"),
                        "debug_artifact_url": debug_url,
                        "debug_artifact_path": str(debug_path) if debug_path else None,
                    },
                )
            )
            if debug_path is not None:
                db.add(
                    WarehouseAsset(
                        model_id=int(model_id),
                        coordinate_frame_id=int(coordinate_frame_id),
                        frame_id="warehouse_map",
                        type=STRUCTURE_DEBUG_ASSET_TYPE,
                        url=debug_url or str(debug_path),
                        checksum=hashlib.sha256(
                            json.dumps(
                                debug_payload,
                                sort_keys=True,
                                separators=(",", ":"),
                                default=_safe_debug_value,
                            ).encode()
                        ).hexdigest(),
                        meta_data={
                            "warehouse_map_id": int(warehouse_map_id),
                            "coordinate_frame_id": int(coordinate_frame_id),
                            "artifact_set_id": int(artifact_set.id),
                            "input_checksum": lineage_checksum,
                            "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                            "client_flight_id": client_flight_id,
                            "failure_reason_codes": failure_reason_codes,
                            "quality_status": quality_status,
                            "path": str(debug_path),
                        },
                    )
                )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("structure_extraction: persistence failed")
            raise RuntimeError(str(exc)) from exc

    return {
        "warehouse_map_id": int(warehouse_map_id),
        "model_id": int(model_id),
        "client_flight_id": client_flight_id,
        "target_count": len(result.targets),
        "active_target_count": active_target_count,
        "review_target_count": review_target_count,
        "rejected_target_count": rejected_target_count,
        "coordinate_setup_status": "active" if active_target_count > 0 else "draft",
        "manual_review_required": quality_status != "ready" or review_target_count > 0,
        "rejected_clearance": result.rejected_clearance,
        "aisles": int(result.summary.get("counts", {}).get("aisles", 0)),
        "racks": int(result.summary.get("counts", {}).get("racks", 0)),
        "status": quality_status,
        "artifact_set_checksum": lineage_checksum,
        "layout_version_id": int(layout.id),
        "layout_published": published,
        "quality_status": quality_status,
        "quality_reasons": list(quality.get("reasons") or []),
        "failure_reason_codes": failure_reason_codes,
        "debug_artifact_url": debug_url,
        "confidence": quality.get("confidence"),
    }


async def extract_and_persist_structure(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    params: StructureExtractionParams | None = None,
) -> dict[str, Any]:
    """Run structure extraction for a flight and persist targets + asset."""
    record_extraction_running(warehouse_map_id=int(warehouse_map_id))
    effective = (params or StructureExtractionParams()).sanitized()
    try:
        coordinate_frame_id: int | None = None
        landmark_validation: dict[str, Any] | None = None
        async with Session() as db:
            coordinate_frame = (
                await db.execute(
                    select(WarehouseCoordinateFrame)
                    .where(
                        WarehouseCoordinateFrame.warehouse_map_id == int(warehouse_map_id),
                        WarehouseCoordinateFrame.status == "locked",
                    )
                    .order_by(WarehouseCoordinateFrame.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if coordinate_frame is None:
            raise RuntimeError("Structure extraction requires a locked warehouse coordinate frame")
        _validate_extraction_coordinate_frame(coordinate_frame)
        async with Session() as db:
            landmark_validation = await _validate_landmark_frame(
                db,
                warehouse_map_id=int(warehouse_map_id),
                coordinate_frame=coordinate_frame,
            )
        coordinate_frame_id = int(coordinate_frame.id)
        await asyncio.to_thread(_validate_manifest_coverage, client_flight_id, effective)
        readiness = await refresh_structure_input_readiness(timeout_s=8.0)
        live_occupancy = occupancy_grid_from_ros_yaml(readiness.occupancy_message)
        logger.info(
            "warehouse_structure_extract_readiness",
            extra={"warehouse_map_id": int(warehouse_map_id), **readiness.to_dict()},
        )
        result = await asyncio.to_thread(
            extract_structure_from_flight,
            client_flight_id,
            params=effective,
            occupancy_grid=live_occupancy,
            odom_to_warehouse_map_transform=coordinate_frame.transform_json,
        )
        _attach_manifest_hints(result, client_flight_id)
        result.summary["diagnostics"] = {
            **readiness.to_dict(),
            "occupancy_snapshot_source": (
                "live_ros" if live_occupancy is not None else "saved_or_geometry_fallback"
            ),
            "worker_ros_env_ok": bool(readiness.esdf_available or readiness.occupancy_available),
        }
        result.summary["landmark_frame_validation"] = landmark_validation or {}
        _force_review_without_clearance_evidence(result)
        _attach_quality_gate(result)
        _record_result_observability(result)
        persisted = await _persist_result(
            warehouse_map_id=warehouse_map_id,
            model_id=model_id,
            client_flight_id=client_flight_id,
            result=result,
            coordinate_frame_id=int(coordinate_frame.id),
        )
        record_extraction_ready(
            warehouse_map_id=int(warehouse_map_id),
            target_count=int(persisted.get("target_count") or 0),
        )
        logger.info(
            "warehouse_coordinate_setup_detection_completed",
            extra={
                "warehouse_map_id": int(warehouse_map_id),
                **persisted,
                "quality_reasons": persisted.get("quality_reasons", []),
            },
        )
        return persisted
    except Exception as exc:
        failure_reason_codes = _failure_reason_codes_from_message(str(exc))
        _record_extraction_failure_metrics(failure_reason_codes)
        failure_checksum = hashlib.sha256(
            json.dumps(
                {
                    "warehouse_map_id": int(warehouse_map_id),
                    "model_id": int(model_id),
                    "client_flight_id": client_flight_id,
                    "error": str(exc),
                    "params": asdict(effective),
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        debug_path, debug_url = await asyncio.to_thread(
            _write_debug_artifact,
            client_flight_id,
            payload=_debug_payload(
                warehouse_map_id=warehouse_map_id,
                model_id=model_id,
                client_flight_id=client_flight_id,
                coordinate_frame_id=locals().get("coordinate_frame_id"),
                result=None,
                lineage_checksum=failure_checksum,
                failure_reason_codes=failure_reason_codes,
                error_message=str(exc),
            ),
            lineage_checksum=failure_checksum,
        )
        logger.warning(
            "warehouse_structure_detection_failed",
            extra={
                "warehouse_map_id": int(warehouse_map_id),
                "model_id": int(model_id),
                "client_flight_id": client_flight_id,
                "failure_reason_codes": failure_reason_codes,
                "debug_artifact_url": debug_url,
                "debug_artifact_path": str(debug_path) if debug_path else None,
            },
        )
        record_extraction_failed(
            warehouse_map_id=int(warehouse_map_id),
            error_message=str(exc),
            failure_reason_codes=failure_reason_codes,
            debug_artifact_url=debug_url,
        )
        raise


async def dry_run_structure_extraction(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    params: StructureExtractionParams | None = None,
) -> dict[str, Any]:
    """Run extraction without writing layout/targets/assets.

    This is intentionally read-only from the database perspective. It still
    writes a downloadable debug artifact next to the flight chunks so operators
    can inspect why the run is not publishable.
    """
    effective = (params or StructureExtractionParams()).sanitized()
    coordinate_frame_id: int | None = None
    landmark_validation: dict[str, Any] | None = None
    try:
        async with Session() as db:
            coordinate_frame = (
                await db.execute(
                    select(WarehouseCoordinateFrame)
                    .where(
                        WarehouseCoordinateFrame.warehouse_map_id == int(warehouse_map_id),
                        WarehouseCoordinateFrame.status == "locked",
                    )
                    .order_by(WarehouseCoordinateFrame.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if coordinate_frame is None:
            raise RuntimeError("Structure extraction requires a locked warehouse coordinate frame")
        _validate_extraction_coordinate_frame(coordinate_frame)
        async with Session() as db:
            landmark_validation = await _validate_landmark_frame(
                db,
                warehouse_map_id=int(warehouse_map_id),
                coordinate_frame=coordinate_frame,
            )
        coordinate_frame_id = int(coordinate_frame.id)
        await asyncio.to_thread(_validate_manifest_coverage, client_flight_id, effective)
        readiness = await refresh_structure_input_readiness(timeout_s=8.0)
        live_occupancy = occupancy_grid_from_ros_yaml(readiness.occupancy_message)
        result = await asyncio.to_thread(
            extract_structure_from_flight,
            client_flight_id,
            params=effective,
            occupancy_grid=live_occupancy,
            odom_to_warehouse_map_transform=coordinate_frame.transform_json,
        )
        _attach_manifest_hints(result, client_flight_id)
        result.summary["diagnostics"] = {
            **readiness.to_dict(),
            "occupancy_snapshot_source": (
                "live_ros" if live_occupancy is not None else "saved_or_geometry_fallback"
            ),
            "worker_ros_env_ok": bool(readiness.esdf_available or readiness.occupancy_available),
        }
        result.summary["landmark_frame_validation"] = landmark_validation or {}
        _force_review_without_clearance_evidence(result)
        _attach_quality_gate(result)
        _record_result_observability(result)
        failure_reason_codes = _quality_failure_reason_codes(result.summary)
        checksum = hashlib.sha256(
            json.dumps(
                {
                    "warehouse_map_id": int(warehouse_map_id),
                    "model_id": int(model_id),
                    "client_flight_id": client_flight_id,
                    "coordinate_frame_id": coordinate_frame_id,
                    "params": asdict(effective),
                    "summary": result.summary,
                },
                sort_keys=True,
                default=_safe_debug_value,
            ).encode()
        ).hexdigest()
        debug_path, debug_url = await asyncio.to_thread(
            _write_debug_artifact,
            client_flight_id,
            payload=_debug_payload(
                warehouse_map_id=warehouse_map_id,
                model_id=model_id,
                client_flight_id=client_flight_id,
                coordinate_frame_id=coordinate_frame_id,
                result=result,
                lineage_checksum=checksum,
                failure_reason_codes=failure_reason_codes,
            ),
            lineage_checksum=checksum,
        )
        quality = result.summary.get("quality")
        quality = quality if isinstance(quality, dict) else {}
        counts = result.summary.get("counts")
        counts = counts if isinstance(counts, dict) else {}
        return {
            "status": quality.get("status") or result.summary.get("status") or "needs_review",
            "warehouse_map_id": int(warehouse_map_id),
            "model_id": int(model_id),
            "client_flight_id": client_flight_id,
            "coordinate_frame_id": coordinate_frame_id,
            "target_count": int(counts.get("candidate_targets") or counts.get("targets") or 0),
            "active_target_count": int(counts.get("active_targets") or 0),
            "review_target_count": int(counts.get("review_targets") or 0),
            "rejected_target_count": int(counts.get("rejected_clearance") or 0),
            "quality_status": quality.get("status"),
            "quality_reasons": list(quality.get("reasons") or []),
            "failure_reason_codes": failure_reason_codes,
            "confidence": quality.get("confidence"),
            "debug_artifact_url": debug_url,
            "debug_artifact_path": str(debug_path) if debug_path else None,
            "summary": result.summary,
        }
    except Exception as exc:
        failure_reason_codes = _failure_reason_codes_from_message(str(exc))
        _record_extraction_failure_metrics(failure_reason_codes)
        checksum = hashlib.sha256(
            json.dumps(
                {
                    "warehouse_map_id": int(warehouse_map_id),
                    "model_id": int(model_id),
                    "client_flight_id": client_flight_id,
                    "error": str(exc),
                    "params": asdict(effective),
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        debug_path, debug_url = await asyncio.to_thread(
            _write_debug_artifact,
            client_flight_id,
            payload=_debug_payload(
                warehouse_map_id=warehouse_map_id,
                model_id=model_id,
                client_flight_id=client_flight_id,
                coordinate_frame_id=coordinate_frame_id,
                result=None,
                lineage_checksum=checksum,
                failure_reason_codes=failure_reason_codes,
                error_message=str(exc),
            ),
            lineage_checksum=checksum,
        )
        return {
            "status": "failed",
            "warehouse_map_id": int(warehouse_map_id),
            "model_id": int(model_id),
            "client_flight_id": client_flight_id,
            "coordinate_frame_id": coordinate_frame_id,
            "target_count": 0,
            "active_target_count": 0,
            "review_target_count": 0,
            "rejected_target_count": 0,
            "quality_status": "failed",
            "quality_reasons": [],
            "failure_reason_codes": failure_reason_codes,
            "confidence": None,
            "debug_artifact_url": debug_url,
            "debug_artifact_path": str(debug_path) if debug_path else None,
            "error_message": str(exc),
            "summary": {},
        }


def _attach_manifest_hints(result: StructureResult, client_flight_id: str) -> None:
    try:
        from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest

        manifest = load_flight_manifest(client_flight_id)
    except Exception:
        logger.debug("structure_extraction_manifest_hints_failed", exc_info=True)
        return
    if manifest is None:
        return
    result.summary["map_quality"] = {
        "manifest_status": manifest.manifest_status,
        "map_quality": manifest.map_quality,
        "default_view_layer": manifest.default_view_layer,
        "rgbd_cloud_available": manifest.rgbd_cloud_available,
        "rgbd_has_rgb": manifest.rgbd_has_rgb,
        "diagnostic_nvblox_layers": list(manifest.diagnostic_nvblox_layers),
        "nvblox_available": bool(manifest.nvblox_available),
        "missing_topics": list(manifest.missing_topics or []),
        "chunk_counts": dict(manifest.chunk_counts or {}),
        "point_counts": dict(getattr(manifest, "point_counts", {}) or {}),
        "source_quality": dict(getattr(manifest, "source_quality", {}) or {}),
        "chunk_quality": list(getattr(manifest, "chunk_quality", []) or []),
        "rack_face_coverage": dict(getattr(manifest, "rack_face_coverage", {}) or {}),
        "coverage_repair": dict(getattr(manifest, "coverage_repair", {}) or {}),
        "tf_degraded": bool(getattr(manifest, "tf_degraded", False)),
        "tf_jump_back_count": int(getattr(manifest, "tf_jump_back_count", 0) or 0),
        "tf_old_data_count": int(getattr(manifest, "tf_old_data_count", 0) or 0),
        "nvblox_restart_count": int(getattr(manifest, "nvblox_restart_count", 0) or 0),
    }
    clearance = result.summary.get("clearance")
    if isinstance(clearance, dict) and not manifest.nvblox_available:
        clearance.setdefault("source", "point_cloud_fallback")
        clearance.setdefault("missing_topics", list(manifest.missing_topics or []))


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


async def resolve_latest_model_flight(
    db,
    *,
    warehouse_map_id: int,
) -> tuple[int, str] | None:
    """Return (model_id, client_flight_id) for the newest ready model of a map.

    Reads the client_flight_id from the mapping job params persisted by
    ``persist_capture``. Returns ``None`` when nothing is extractable yet.
    """
    from backend.modules.warehouse.models import WarehouseMappingJob

    rows = (
        await db.execute(
            select(WarehouseMappingJob, WarehouseModel)
            .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
            .where(
                WarehouseMappingJob.warehouse_map_id == int(warehouse_map_id),
                WarehouseModel.status == "ready",
            )
            .order_by(WarehouseMappingJob.id.desc())
            .limit(10)
        )
    ).all()
    for job, model in rows:
        params = job.params if isinstance(job.params, dict) else {}
        capture = params.get("capture_result")
        capture = capture if isinstance(capture, dict) else {}
        flight = capture.get("client_flight_id") or params.get("client_flight_id")
        token = str(flight or "").strip()
        if token:
            return int(model.id), token
    return None
