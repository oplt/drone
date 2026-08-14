"""Live-map flight manifest — build manifest from on-disk chunks."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from backend.core.config.runtime import settings
from backend.modules.warehouse.service.map_source_config import WAREHOUSE_LIVE_MAP_SOURCES

from .chunk_ids import _infer_source_from_chunk_id
from .chunk_quality import _chunk_quality_entry
from .coercion import _safe_int
from .coverage import build_coverage_repair_waypoints, build_rack_face_coverage
from .deps import resolve, resolve_chunk_storage
from .models import LiveMapFlightManifest
from .storage_access import _iter_stored_chunks

logger = logging.getLogger(__name__)


def build_manifest_from_flight_dir(
    flight_id: str,
    *,
    missing_topics: list[str] | None = None,
    localization_ok: bool = True,
    diagnostics_phase: str = "pre_finalize",
) -> LiveMapFlightManifest:
    safe_flight = str(flight_id or "").strip()
    chunk_counts: dict[str, int] = {}
    point_counts: dict[str, int] = {}
    bbox_by_source: dict[str, list[float]] = {}
    seen_ids: set[str] = set()
    rgbd_has_rgb = False
    source_topics: dict[str, str] = {}
    source_paths: dict[str, str] = {}
    chunk_quality: list[dict[str, Any]] = []
    frame_id = "odom"
    storage = resolve_chunk_storage()

    for stored in _iter_stored_chunks(safe_flight):
        chunk_id = str(getattr(stored, "chunk_id", "") or "")
        if not chunk_id or chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        sidecar = (
            storage.load_chunk_metadata(
                flight_id=safe_flight,
                chunk_id=chunk_id,
            )
            or {}
        )
        source = str(sidecar.get("source") or _infer_source_from_chunk_id(chunk_id))
        if source == "rgbd_colored" and not bool(sidecar.get("has_rgb")):
            source = "rgbd_xyz_uncolored"
        stored_path = str(getattr(stored, "path", "") or "")
        chunk_quality.append(
            _chunk_quality_entry(
                chunk_id=chunk_id,
                source=source,
                stored_path=stored_path,
                sidecar=sidecar,
            )
        )
        chunk_counts[source] = chunk_counts.get(source, 0) + 1
        if sidecar.get("source_topic"):
            source_topics[source] = str(sidecar["source_topic"])
        source_paths.setdefault(source, str(getattr(stored, "path", "") or ""))
        if sidecar.get("frame_id"):
            frame_id = str(sidecar["frame_id"])
        points = _safe_int(sidecar.get("point_count"), 0)
        if points > 0:
            point_counts[source] = point_counts.get(source, 0) + points
        bbox = sidecar.get("bbox_local_m")
        if isinstance(bbox, list) and len(bbox) == 6:
            try:
                values = [float(v) for v in bbox]
            except (TypeError, ValueError):
                values = []
            if values and all(v == v for v in values):
                current = bbox_by_source.get(source)
                if current is None:
                    bbox_by_source[source] = values
                else:
                    bbox_by_source[source] = [
                        min(current[0], values[0]),
                        min(current[1], values[1]),
                        min(current[2], values[2]),
                        max(current[3], values[3]),
                        max(current[4], values[4]),
                        max(current[5], values[5]),
                    ]
        if source == "rgbd_colored" and bool(sidecar.get("has_rgb")):
            rgbd_has_rgb = True

    rgbd_colored_count = chunk_counts.get("rgbd_colored", 0)
    rgbd_xyz_count = chunk_counts.get("rgbd_xyz_uncolored", 0)
    nvblox_product_count = sum(
        chunk_counts.get(key, 0)
        for key in (
            "nvblox_esdf",
            "nvblox_mesh",
            "nvblox_occupancy",
        )
    )
    diagnostic_nvblox_layers = [
        key for key in ("nvblox_color", "nvblox_tsdf") if chunk_counts.get(key, 0) > 0
    ]
    nvblox_count = nvblox_product_count + sum(
        chunk_counts.get(key, 0) for key in diagnostic_nvblox_layers
    )
    raw_count = chunk_counts.get("mid360_raw", 0)
    rgbd_cloud_available = rgbd_colored_count > 0 or rgbd_xyz_count > 0
    user_map_available = rgbd_cloud_available or nvblox_product_count > 0
    raw_only = raw_count > 0 and not user_map_available

    if rgbd_colored_count > 0:
        quality = "rgbd_colored"
        default_view_layer = "rgbd_colored"
    elif rgbd_xyz_count > 0:
        quality = "rgbd_xyz_uncolored"
        default_view_layer = "rgbd_xyz_uncolored"
    elif chunk_counts.get("nvblox_esdf", 0) > 0:
        quality = "nvblox_esdf"
        default_view_layer = "nvblox_esdf"
    elif chunk_counts.get("nvblox_mesh", 0) > 0:
        quality = "nvblox_mesh"
        default_view_layer = "nvblox_mesh"
    elif raw_only:
        quality = "raw_lidar"
        default_view_layer = "mid360_raw"
    else:
        quality = "empty"
        default_view_layer = None

    if resolve("require_rgb_for_save")() and raw_only:
        quality = "degraded_raw_only"

    localization_quality = "ok" if localization_ok else "degraded"
    quality_evidence = user_map_available
    source_quality: dict[str, dict[str, Any]] = {}
    for source, bbox in bbox_by_source.items():
        dx = max(0.0, float(bbox[3]) - float(bbox[0]))
        dy = max(0.0, float(bbox[4]) - float(bbox[1]))
        dz = max(0.0, float(bbox[5]) - float(bbox[2]))
        floor_area = dx * dy
        source_quality[source] = {
            "bbox_local_m": [round(float(v), 3) for v in bbox],
            "bbox_volume_m3": round(dx * dy * dz, 3),
            "floor_area_m2": round(floor_area, 3),
            "points_per_m2": round(float(point_counts.get(source, 0)) / floor_area, 3)
            if floor_area > 0
            else 0.0,
        }

    captured_topics = {
        WAREHOUSE_LIVE_MAP_SOURCES[source].topic
        for source, count in chunk_counts.items()
        if count > 0 and source in WAREHOUSE_LIVE_MAP_SOURCES
    }
    captured_topics.update(
        {
            "/nvblox_node/static_map_slice"
            for source, count in chunk_counts.items()
            if source == "nvblox_occupancy" and count > 0
        }
    )
    reconciled_missing_topics = [
        topic for topic in list(missing_topics or []) if topic not in captured_topics
    ]

    tf_degraded = False
    tf_jump_back_count = 0
    tf_old_data_count = 0
    nvblox_restart_count = 0
    try:
        from backend.modules.warehouse.service.nvblox_log_parser import nvblox_log_parser
        from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker

        tracker = nvblox_status_tracker.as_dict()
        parser = nvblox_log_parser.as_dict()
        tf_degraded = bool(tracker.get("tf_degraded"))
        tf_jump_back_count = max(
            _safe_int(tracker.get("tf_jump_back_count")),
            _safe_int(parser.get("tf_jump_back_count")),
        )
        tf_old_data_count = max(
            _safe_int(tracker.get("tf_old_data_count")),
            _safe_int(parser.get("tf_old_data_count")),
        )
        nvblox_restart_count = _safe_int(parser.get("restart_count"))
    except Exception:
        logger.debug("live_map_manifest_tf_health_probe_failed", exc_info=True)

    rack_face_coverage = build_rack_face_coverage(
        chunk_quality,
        min_points_per_m2=float(settings.warehouse_structure_min_surface_points_per_m2 or 0.0),
        require_rgb=False,
        require_esdf=True,
    )
    coverage_repair = build_coverage_repair_waypoints(rack_face_coverage)

    return LiveMapFlightManifest(
        flight_id=safe_flight,
        generated_at=datetime.now(UTC).isoformat(),
        chunk_counts=chunk_counts,
        point_counts=point_counts,
        rgbd_colored_available=rgbd_colored_count > 0 and rgbd_has_rgb,
        rgbd_cloud_available=rgbd_cloud_available,
        rgbd_has_rgb=rgbd_has_rgb,
        nvblox_available=nvblox_count > 0,
        raw_lidar_only=raw_only,
        localization_ok=localization_ok,
        localization_quality=localization_quality,
        quality_evidence=quality_evidence,
        missing_topics=reconciled_missing_topics,
        map_quality=quality,
        default_view_layer=default_view_layer,
        diagnostic_nvblox_layers=diagnostic_nvblox_layers,
        esdf_available=chunk_counts.get("nvblox_esdf", 0) > 0,
        esdf_topic=source_topics.get("nvblox_esdf"),
        esdf_pointcloud_path=source_paths.get("nvblox_esdf"),
        occupancy_available=chunk_counts.get("nvblox_occupancy", 0) > 0,
        occupancy_topic=source_topics.get("nvblox_occupancy"),
        occupancy_grid_path=source_paths.get("nvblox_occupancy"),
        frame_id=frame_id,
        coordinate_frame=frame_id,
        source_quality=source_quality,
        chunk_quality=chunk_quality,
        rack_face_coverage=rack_face_coverage,
        coverage_repair=coverage_repair,
        tf_degraded=tf_degraded,
        tf_jump_back_count=tf_jump_back_count,
        tf_old_data_count=tf_old_data_count,
        nvblox_restart_count=nvblox_restart_count,
        diagnostics_phase=diagnostics_phase,
    )


__all__ = ["build_manifest_from_flight_dir"]
