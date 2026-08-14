"""Async orchestration for warehouse structure extraction."""

from __future__ import annotations

from backend.core.config.runtime import settings

from .deps import load_flight_manifest, warehouse_live_map_chunk_storage
from .flight_resolution import resolve_latest_model_flight

from .artifacts import (
    _debug_payload,
    _hash_input_file,
    _scan_artifact_lineage,
    _write_debug_artifact,
)
from .constants import (
    EXTRACTION_TASK_NAME,
    STRUCTURE_ASSET_TYPE,
    STRUCTURE_DEBUG_ASSET_TYPE,
    STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
    _EXTRACTION_CELERY_PROBE_AT,
    _EXTRACTION_STATE,
    _WORKER_READY_CACHE,
)
from .failure_codes import (
    _failure_reason_codes_from_message,
    _quality_failure_reason_codes,
    _record_extraction_failure_metrics,
)
from .manifest_hints import _attach_manifest_hints
from .orchestrator import dry_run_structure_extraction, extract_and_persist_structure
from .parameters import params_from_payload
from .persist import _persist_result
from .quality import (
    _attach_quality_gate,
    _force_review_without_clearance_evidence,
    _refresh_target_counts,
    ensure_structure_quality_summary,
)
from .repository import (
    create_durable_extraction_job,
    get_durable_extraction_state,
    update_durable_extraction_job,
)
from .state_store import (
    get_extraction_state,
    record_extraction_failed,
    record_extraction_queued,
    record_extraction_ready,
    record_extraction_running,
)
from .validation import (
    _validate_extraction_coordinate_frame,
    _validate_landmark_frame,
    _validate_manifest_coverage,
)
from .worker_health import (
    clear_mapping_worker_heartbeat,
    record_mapping_worker_heartbeat,
    warehouse_mapping_worker_ready,
)

__all__ = [
    "EXTRACTION_TASK_NAME",
    "STRUCTURE_ASSET_TYPE",
    "STRUCTURE_DEBUG_ASSET_TYPE",
    "STRUCTURE_EXTRACTION_ALGORITHM_VERSION",
    "_EXTRACTION_CELERY_PROBE_AT",
    "_EXTRACTION_STATE",
    "_WORKER_READY_CACHE",
    "_attach_manifest_hints",
    "_attach_quality_gate",
    "_debug_payload",
    "_failure_reason_codes_from_message",
    "_force_review_without_clearance_evidence",
    "_hash_input_file",
    "_persist_result",
    "_quality_failure_reason_codes",
    "_record_extraction_failure_metrics",
    "_refresh_target_counts",
    "_scan_artifact_lineage",
    "_validate_extraction_coordinate_frame",
    "_validate_landmark_frame",
    "_validate_manifest_coverage",
    "_write_debug_artifact",
    "clear_mapping_worker_heartbeat",
    "create_durable_extraction_job",
    "dry_run_structure_extraction",
    "ensure_structure_quality_summary",
    "extract_and_persist_structure",
    "get_durable_extraction_state",
    "get_extraction_state",
    "load_flight_manifest",
    "params_from_payload",
    "record_extraction_failed",
    "record_extraction_queued",
    "record_extraction_ready",
    "record_extraction_running",
    "record_mapping_worker_heartbeat",
    "resolve_latest_model_flight",
    "settings",
    "update_durable_extraction_job",
    "warehouse_live_map_chunk_storage",
    "warehouse_mapping_worker_ready",
]
