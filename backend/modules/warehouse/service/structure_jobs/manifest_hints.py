"""Attach live-map manifest hints to structure extraction results."""

from __future__ import annotations

import logging

from backend.modules.warehouse.service.structure_extraction import StructureResult

from .deps import resolve_load_flight_manifest

logger = logging.getLogger(__name__)


def _attach_manifest_hints(result: StructureResult, client_flight_id: str) -> None:
    try:
        manifest = resolve_load_flight_manifest()(client_flight_id)
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
