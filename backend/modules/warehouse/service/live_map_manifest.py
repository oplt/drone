from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.core.config.runtime import settings
from backend.modules.warehouse.service.live_map_config import require_rgb_for_save
from backend.modules.warehouse.service.live_map_storage import warehouse_live_map_chunk_storage
from backend.modules.warehouse.service.map_source_config import WAREHOUSE_LIVE_MAP_SOURCES

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "live_map_manifest.json"
_CHUNK_ID_RE = re.compile(
    r"^(rgbd|rgbd_colored|rgbd_xyz|mid360|mid360_raw|nvblox_color|nvblox_esdf|"
    r"nvblox_tsdf|nvblox_mesh|nvblox_occupancy)_",
    re.IGNORECASE,
)


@dataclass
class LiveMapFlightManifest:
    flight_id: str
    generated_at: str
    chunk_counts: dict[str, int] = field(default_factory=dict)
    point_counts: dict[str, int] = field(default_factory=dict)
    rgbd_colored_available: bool = False
    rgbd_cloud_available: bool = False
    rgbd_has_rgb: bool = False
    nvblox_available: bool = False
    raw_lidar_only: bool = False
    localization_ok: bool = True
    localization_quality: str = "ok"
    quality_evidence: bool = False
    missing_topics: list[str] = field(default_factory=list)
    map_quality: str = "unknown"
    default_view_layer: str | None = None
    diagnostic_nvblox_layers: list[str] = field(default_factory=list)
    esdf_available: bool = False
    esdf_topic: str | None = None
    esdf_pointcloud_path: str | None = None
    occupancy_available: bool = False
    occupancy_topic: str | None = None
    occupancy_grid_path: str | None = None
    frame_id: str = "odom"
    coordinate_frame: str = "odom"
    source_quality: dict[str, dict[str, Any]] = field(default_factory=dict)
    chunk_quality: list[dict[str, Any]] = field(default_factory=list)
    rack_face_coverage: dict[str, Any] = field(default_factory=dict)
    coverage_repair: dict[str, Any] = field(default_factory=dict)
    tf_degraded: bool = False
    tf_jump_back_count: int = 0
    tf_old_data_count: int = 0
    nvblox_restart_count: int = 0
    diagnostics_phase: str = "pre_finalize"
    manifest_status: str = "complete"
    missing_chunks: list[str] = field(default_factory=list)
    total_bytes: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "flight_id": self.flight_id,
            "generated_at": self.generated_at,
            "chunk_counts": dict(self.chunk_counts),
            "point_counts": dict(self.point_counts),
            "rgbd_colored_available": self.rgbd_colored_available,
            "rgbd_cloud_available": self.rgbd_cloud_available,
            "rgbd_has_rgb": self.rgbd_has_rgb,
            "nvblox_available": self.nvblox_available,
            "raw_lidar_only": self.raw_lidar_only,
            "localization_ok": self.localization_ok,
            "localization_quality": self.localization_quality,
            "quality_evidence": self.quality_evidence,
            "missing_topics": list(self.missing_topics),
            "map_quality": self.map_quality,
            "default_view_layer": self.default_view_layer,
            "diagnostic_nvblox_layers": list(self.diagnostic_nvblox_layers),
            "esdf_available": self.esdf_available,
            "esdf_topic": self.esdf_topic,
            "esdf_pointcloud_path": self.esdf_pointcloud_path,
            "occupancy_available": self.occupancy_available,
            "occupancy_topic": self.occupancy_topic,
            "occupancy_grid_path": self.occupancy_grid_path,
            "frame_id": self.frame_id,
            "coordinate_frame": self.coordinate_frame,
            "source_quality": dict(self.source_quality),
            "chunk_quality": list(self.chunk_quality),
            "rack_face_coverage": dict(self.rack_face_coverage),
            "coverage_repair": dict(self.coverage_repair),
            "tf_degraded": bool(self.tf_degraded),
            "tf_jump_back_count": int(self.tf_jump_back_count),
            "tf_old_data_count": int(self.tf_old_data_count),
            "nvblox_restart_count": int(self.nvblox_restart_count),
            "diagnostics_phase": self.diagnostics_phase,
            "manifest_status": self.manifest_status,
            "missing_chunks": list(self.missing_chunks),
            "total_bytes": int(self.total_bytes),
        }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        result[str(key)] = max(0, _safe_int(raw, 0))
    return result


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _safe_nested_dict(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, raw in value.items():
        if isinstance(raw, dict):
            result[str(key)] = dict(raw)
    return result


def _safe_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def _point_from_sidecar(sidecar: dict[str, Any], key: str) -> list[float] | None:
    raw = sidecar.get(key)
    if isinstance(raw, dict):
        try:
            return [float(raw["x"]), float(raw["y"]), float(raw.get("z", 0.0))]
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(raw, list | tuple) and len(raw) >= 2:
        try:
            return [
                float(raw[0]),
                float(raw[1]),
                float(raw[2]) if len(raw) > 2 else 0.0,
            ]
        except (TypeError, ValueError):
            return None
    return None


def _normal_from_sidecar(sidecar: dict[str, Any]) -> list[float] | None:
    return _point_from_sidecar(sidecar, "rack_face_normal") or _point_from_sidecar(
        sidecar, "face_normal"
    )


def _chunk_quality_entry(
    *,
    chunk_id: str,
    source: str,
    stored_path: str,
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "chunk_id": chunk_id,
        "source": source,
        "path": stored_path,
        "point_count": max(0, _safe_int(sidecar.get("point_count"), 0)),
        "has_rgb": bool(sidecar.get("has_rgb")),
    }
    for key in ("source_topic", "frame_id", "encoding", "layer", "layer_type"):
        if sidecar.get(key):
            entry[key] = str(sidecar[key])
    bbox = sidecar.get("bbox_local_m")
    if isinstance(bbox, list) and len(bbox) == 6:
        try:
            entry["bbox_local_m"] = [round(float(v), 3) for v in bbox]
        except (TypeError, ValueError):
            pass
    face_id = sidecar.get("rack_face_id") or sidecar.get("face_id")
    if face_id:
        entry["rack_face_id"] = str(face_id)
    center = _point_from_sidecar(sidecar, "rack_face_center") or _point_from_sidecar(
        sidecar, "face_center"
    )
    if center is not None:
        entry["rack_face_center_m"] = [round(float(v), 3) for v in center]
    normal = _normal_from_sidecar(sidecar)
    if normal is not None:
        entry["rack_face_normal"] = [round(float(v), 4) for v in normal]
    for key in ("viewing_angle_deg", "incidence_angle_deg"):
        if sidecar.get(key) is not None:
            entry[key] = round(_safe_float(sidecar.get(key)), 3)
            break
    return entry


def build_rack_face_coverage(
    chunk_quality: list[dict[str, Any]],
    *,
    min_points_per_m2: float = 15.0,
    max_viewing_angle_deg: float = 65.0,
    require_rgb: bool = False,
    require_esdf: bool = True,
) -> dict[str, Any]:
    """Aggregate chunk sidecars into operator-facing rack-face coverage bins."""
    faces: dict[str, dict[str, Any]] = {}
    global_esdf = any(str(item.get("source")) == "nvblox_esdf" for item in chunk_quality)
    for item in chunk_quality:
        face_id = item.get("rack_face_id")
        if not face_id:
            continue
        key = str(face_id)
        face = faces.setdefault(
            key,
            {
                "rack_face_id": key,
                "point_count": 0,
                "chunk_count": 0,
                "rgb_available": False,
                "esdf_available": False,
                "sources": [],
                "viewing_angles_deg": [],
            },
        )
        face["chunk_count"] = int(face["chunk_count"]) + 1
        face["point_count"] = int(face["point_count"]) + max(
            0, _safe_int(item.get("point_count"), 0)
        )
        source = str(item.get("source") or "unknown")
        if source not in face["sources"]:
            face["sources"].append(source)
        if bool(item.get("has_rgb")):
            face["rgb_available"] = True
        if source in {"nvblox_esdf", "nvblox_occupancy"}:
            face["esdf_available"] = True
        if item.get("rack_face_center_m") and "center_m" not in face:
            face["center_m"] = list(item["rack_face_center_m"])
        if item.get("rack_face_normal") and "normal" not in face:
            face["normal"] = list(item["rack_face_normal"])
        angle = item.get("viewing_angle_deg", item.get("incidence_angle_deg"))
        if angle is not None:
            face["viewing_angles_deg"].append(round(_safe_float(angle), 3))
        bbox = item.get("bbox_local_m")
        if isinstance(bbox, list) and len(bbox) == 6:
            current = face.get("bbox_local_m")
            if not isinstance(current, list) or len(current) != 6:
                face["bbox_local_m"] = list(bbox)
            else:
                face["bbox_local_m"] = [
                    min(float(current[0]), float(bbox[0])),
                    min(float(current[1]), float(bbox[1])),
                    min(float(current[2]), float(bbox[2])),
                    max(float(current[3]), float(bbox[3])),
                    max(float(current[4]), float(bbox[4])),
                    max(float(current[5]), float(bbox[5])),
                ]

    face_rows: list[dict[str, Any]] = []
    for face in faces.values():
        bbox = face.get("bbox_local_m")
        if isinstance(bbox, list) and len(bbox) == 6:
            area = max(0.0, abs(float(bbox[3]) - float(bbox[0]))) * max(
                0.0, abs(float(bbox[5]) - float(bbox[2]))
            )
        else:
            area = 0.0
        points_per_m2 = float(face["point_count"]) / area if area > 0 else 0.0
        angles = face.get("viewing_angles_deg")
        best_angle = min(float(v) for v in angles) if angles else None
        reasons: list[str] = []
        if points_per_m2 < float(min_points_per_m2):
            reasons.append("low_point_density")
        if best_angle is not None and best_angle > float(max_viewing_angle_deg):
            reasons.append("poor_viewing_angle")
        if require_rgb and not bool(face.get("rgb_available")):
            reasons.append("missing_rgb")
        if require_esdf and not (bool(face.get("esdf_available")) or global_esdf):
            reasons.append("missing_esdf")
        face_rows.append(
            {
                **face,
                "floor_area_m2": round(area, 3),
                "points_per_m2": round(points_per_m2, 3),
                "best_viewing_angle_deg": round(best_angle, 3) if best_angle is not None else None,
                "status": "covered" if not reasons else "uncovered",
                "reasons": reasons,
            }
        )
    face_rows.sort(key=lambda item: str(item.get("rack_face_id")))
    covered = sum(1 for item in face_rows if item["status"] == "covered")
    return {
        "faces": face_rows,
        "face_count": len(face_rows),
        "covered_face_count": covered,
        "uncovered_face_count": len(face_rows) - covered,
        "coverage_ratio": round(covered / len(face_rows), 3) if face_rows else None,
        "thresholds": {
            "min_points_per_m2": float(min_points_per_m2),
            "max_viewing_angle_deg": float(max_viewing_angle_deg),
            "require_rgb": bool(require_rgb),
            "require_esdf": bool(require_esdf),
        },
    }


def build_coverage_repair_waypoints(
    rack_face_coverage: dict[str, Any],
    *,
    standoff_m: float = 1.2,
) -> dict[str, Any]:
    waypoints: list[dict[str, Any]] = []
    faces = rack_face_coverage.get("faces") if isinstance(rack_face_coverage, dict) else []
    for face in faces if isinstance(faces, list) else []:
        if not isinstance(face, dict) or face.get("status") == "covered":
            continue
        center = face.get("center_m")
        normal = face.get("normal")
        if not (
            isinstance(center, list)
            and len(center) >= 3
            and isinstance(normal, list)
            and len(normal) >= 2
        ):
            continue
        nx, ny = _safe_float(normal[0]), _safe_float(normal[1])
        length = max((nx * nx + ny * ny) ** 0.5, 1e-6)
        nx, ny = nx / length, ny / length
        x = _safe_float(center[0]) + nx * float(standoff_m)
        y = _safe_float(center[1]) + ny * float(standoff_m)
        waypoints.append(
            {
                "rack_face_id": str(face.get("rack_face_id")),
                "pose_local_m": {
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "z": round(_safe_float(center[2], 1.5), 3),
                    "yaw_deg": round(math.degrees(math.atan2(-ny, -nx)), 2),
                    "frame_id": "warehouse_map",
                },
                "reasons": list(face.get("reasons") or []),
            }
        )
    return {
        "uncovered_rack_faces": [
            str(face.get("rack_face_id"))
            for face in faces
            if isinstance(face, dict) and face.get("status") == "uncovered"
        ]
        if isinstance(faces, list)
        else [],
        "extra_pass_waypoints": waypoints,
        "waypoint_count": len(waypoints),
    }


def _infer_source_from_chunk_id(chunk_id: str) -> str:
    lower = chunk_id.lower()
    if lower.startswith("rgbd_xyz_"):
        return "rgbd_xyz_uncolored"
    if lower.startswith(("rgbd_colored_", "rgbd_")):
        return "rgbd_colored"
    if lower.startswith(("mid360_raw_", "mid360_")):
        return "mid360_raw"
    if lower.startswith("nvblox_color_"):
        return "nvblox_color"
    if lower.startswith("nvblox_esdf_"):
        return "nvblox_esdf"
    if lower.startswith("nvblox_tsdf_"):
        return "nvblox_tsdf"
    if lower.startswith("nvblox_mesh_"):
        return "nvblox_mesh"
    if lower.startswith("nvblox_occupancy_"):
        return "nvblox_occupancy"
    return "unknown"


def _chunk_id_from_path(path: Path) -> str | None:
    name = path.name.lower()
    if name.endswith(".meta.json") or name.endswith(".uploading") or name.endswith(".preview.json"):
        return None
    chunk_id = path.stem.rsplit("-", 1)[0]
    if not _CHUNK_ID_RE.match(chunk_id):
        return None
    return chunk_id


def _flight_root(flight_id: str) -> Path:
    if hasattr(warehouse_live_map_chunk_storage, "flight_dir"):
        return warehouse_live_map_chunk_storage.flight_dir(flight_id)  # type: ignore[attr-defined]
    return (warehouse_live_map_chunk_storage.root / str(flight_id).strip()).resolve()


def _iter_stored_chunks(flight_id: str) -> Iterable[Any]:
    if hasattr(warehouse_live_map_chunk_storage, "iter_chunk_files"):
        yield from warehouse_live_map_chunk_storage.iter_chunk_files(flight_id=flight_id)  # type: ignore[attr-defined]
        return
    root = _flight_root(flight_id)
    if not root.exists():
        return
    seen: set[str] = set()
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        chunk_id = _chunk_id_from_path(path)
        if chunk_id is None or chunk_id in seen:
            continue
        seen.add(chunk_id)
        stored = warehouse_live_map_chunk_storage.resolve(flight_id=flight_id, chunk_id=chunk_id)
        if stored is not None:
            yield stored


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

    for stored in _iter_stored_chunks(safe_flight):
        chunk_id = str(getattr(stored, "chunk_id", "") or "")
        if not chunk_id or chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        sidecar = (
            warehouse_live_map_chunk_storage.load_chunk_metadata(
                flight_id=safe_flight,
                chunk_id=chunk_id,
            )
            or {}
        )
        source = str(sidecar.get("source") or _infer_source_from_chunk_id(chunk_id))
        if source == "rgbd_colored" and not bool(sidecar.get("has_rgb")):
            # Normalize legacy chunks whose source name claimed color despite XYZ-only data.
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

    if require_rgb_for_save() and raw_only:
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


def validate_manifest_chunk_files(
    flight_id: str,
    *,
    chunk_ids: list[str] | None = None,
) -> tuple[list[str], int]:
    """Return missing chunk ids and total on-disk bytes for resolved chunks."""
    safe_flight = str(flight_id or "").strip()
    if chunk_ids is None:
        chunk_ids = [str(stored.chunk_id) for stored in _iter_stored_chunks(safe_flight)]

    missing: list[str] = []
    total_bytes = 0
    seen: set[str] = set()
    for raw_chunk_id in chunk_ids:
        chunk_id = str(raw_chunk_id or "").strip()
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        stored = warehouse_live_map_chunk_storage.resolve(
            flight_id=safe_flight,
            chunk_id=chunk_id,
        )
        if stored is None:
            missing.append(chunk_id)
            continue
        total_bytes += max(0, int(stored.byte_size))
    return missing, total_bytes


def finalize_manifest_integrity(manifest: LiveMapFlightManifest) -> LiveMapFlightManifest:
    missing, total_bytes = validate_manifest_chunk_files(manifest.flight_id)
    manifest.missing_chunks = missing
    manifest.total_bytes = total_bytes
    if missing:
        manifest.manifest_status = "partial"
        logger.warning(
            "live_map_manifest_partial flight_id=%s missing_chunks=%s "
            "total_bytes=%s chunk_counts=%s point_counts=%s",
            manifest.flight_id,
            missing,
            total_bytes,
            manifest.chunk_counts,
            manifest.point_counts,
        )
    else:
        manifest.manifest_status = "complete"
        logger.info(
            "live_map_manifest_finalized flight_id=%s chunk_counts=%s "
            "point_counts=%s total_bytes=%s",
            manifest.flight_id,
            manifest.chunk_counts,
            manifest.point_counts,
            total_bytes,
        )
    return manifest


def validate_save_quality(manifest: LiveMapFlightManifest) -> tuple[bool, str]:
    if manifest.map_quality == "empty":
        return False, "No live-map chunks were persisted for this flight."
    if manifest.manifest_status == "partial":
        return (
            False,
            f"Live-map manifest is partial; missing {len(manifest.missing_chunks)} chunk file(s).",
        )
    if require_rgb_for_save() and manifest.raw_lidar_only:
        return False, (
            "Map save degraded: only raw Mid360 LiDAR chunks exist; "
            "RGB-D or nvBlox colored data is required."
        )
    if manifest.raw_lidar_only:
        return True, "Saved map contains raw LiDAR only (debug/fallback)."
    return True, "Saved map contains colored RGB-D and/or nvBlox layers."
