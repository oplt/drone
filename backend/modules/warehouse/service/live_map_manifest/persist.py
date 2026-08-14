"""Live-map flight manifest — save and load."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .coercion import (
    _safe_dict,
    _safe_dict_list,
    _safe_int,
    _safe_nested_dict,
    _safe_str_list,
)
from .constants import _MANIFEST_NAME
from .models import LiveMapFlightManifest
from .storage_access import _flight_root

logger = logging.getLogger(__name__)


def save_flight_manifest(manifest: LiveMapFlightManifest) -> Path:
    root = _flight_root(manifest.flight_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / _MANIFEST_NAME
    encoded = json.dumps(manifest.as_dict(), indent=2, sort_keys=True).encode("utf-8")
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_bytes(encoded)
    temp_path.replace(path)
    return path


def load_flight_manifest(flight_id: str) -> LiveMapFlightManifest | None:
    path = _flight_root(flight_id) / _MANIFEST_NAME
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not load live-map manifest flight_id=%s path=%s", flight_id, path)
        return None
    if not isinstance(payload, dict):
        return None
    return LiveMapFlightManifest(
        flight_id=str(payload.get("flight_id") or flight_id),
        generated_at=str(payload.get("generated_at") or ""),
        chunk_counts=_safe_dict(payload.get("chunk_counts")),
        point_counts=_safe_dict(payload.get("point_counts")),
        rgbd_colored_available=bool(payload.get("rgbd_colored_available")),
        rgbd_cloud_available=bool(
            payload.get("rgbd_cloud_available", payload.get("rgbd_colored_available"))
        ),
        rgbd_has_rgb=bool(payload.get("rgbd_has_rgb")),
        nvblox_available=bool(payload.get("nvblox_available")),
        raw_lidar_only=bool(payload.get("raw_lidar_only")),
        localization_ok=bool(payload.get("localization_ok", True)),
        localization_quality=str(payload.get("localization_quality") or "ok"),
        quality_evidence=bool(payload.get("quality_evidence")),
        missing_topics=_safe_str_list(payload.get("missing_topics")),
        map_quality=str(payload.get("map_quality") or "unknown"),
        default_view_layer=(
            str(payload["default_view_layer"]) if payload.get("default_view_layer") else None
        ),
        diagnostic_nvblox_layers=_safe_str_list(payload.get("diagnostic_nvblox_layers")),
        esdf_available=bool(payload.get("esdf_available")),
        esdf_topic=str(payload["esdf_topic"]) if payload.get("esdf_topic") else None,
        esdf_pointcloud_path=(
            str(payload["esdf_pointcloud_path"])
            if payload.get("esdf_pointcloud_path")
            else None
        ),
        occupancy_available=bool(payload.get("occupancy_available")),
        occupancy_topic=(
            str(payload["occupancy_topic"]) if payload.get("occupancy_topic") else None
        ),
        occupancy_grid_path=(
            str(payload["occupancy_grid_path"])
            if payload.get("occupancy_grid_path")
            else None
        ),
        frame_id=str(payload.get("frame_id") or "odom"),
        coordinate_frame=str(payload.get("coordinate_frame") or "odom"),
        source_quality=_safe_nested_dict(payload.get("source_quality")),
        chunk_quality=_safe_dict_list(payload.get("chunk_quality")),
        rack_face_coverage=(
            dict(payload.get("rack_face_coverage"))
            if isinstance(payload.get("rack_face_coverage"), dict)
            else {}
        ),
        coverage_repair=(
            dict(payload.get("coverage_repair"))
            if isinstance(payload.get("coverage_repair"), dict)
            else {}
        ),
        tf_degraded=bool(payload.get("tf_degraded", False)),
        tf_jump_back_count=max(0, _safe_int(payload.get("tf_jump_back_count"), 0)),
        tf_old_data_count=max(0, _safe_int(payload.get("tf_old_data_count"), 0)),
        nvblox_restart_count=max(0, _safe_int(payload.get("nvblox_restart_count"), 0)),
        diagnostics_phase=str(payload.get("diagnostics_phase") or "unknown"),
        manifest_status=str(payload.get("manifest_status") or "complete"),
        missing_chunks=_safe_str_list(payload.get("missing_chunks")),
        total_bytes=max(0, _safe_int(payload.get("total_bytes"), 0)),
    )


__all__ = ["load_flight_manifest", "save_flight_manifest"]
