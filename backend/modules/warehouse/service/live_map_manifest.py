from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.modules.warehouse.service.live_map_config import require_rgb_for_save
from backend.modules.warehouse.service.live_map_storage import warehouse_live_map_chunk_storage

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "live_map_manifest.json"
_CHUNK_ID_RE = re.compile(
    r"^(rgbd|rgbd_colored|mid360|mid360_raw|nvblox_color|nvblox_esdf|"
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
    rgbd_has_rgb: bool = False
    nvblox_available: bool = False
    raw_lidar_only: bool = False
    localization_ok: bool = True
    localization_quality: str = "ok"
    quality_evidence: bool = False
    missing_topics: list[str] = field(default_factory=list)
    map_quality: str = "unknown"
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
            "rgbd_has_rgb": self.rgbd_has_rgb,
            "nvblox_available": self.nvblox_available,
            "raw_lidar_only": self.raw_lidar_only,
            "localization_ok": self.localization_ok,
            "localization_quality": self.localization_quality,
            "quality_evidence": self.quality_evidence,
            "missing_topics": list(self.missing_topics),
            "map_quality": self.map_quality,
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


def _infer_source_from_chunk_id(chunk_id: str) -> str:
    lower = chunk_id.lower()
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
    seen_ids: set[str] = set()
    rgbd_has_rgb = False

    for stored in _iter_stored_chunks(safe_flight):
        chunk_id = str(getattr(stored, "chunk_id", "") or "")
        if not chunk_id or chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        sidecar = warehouse_live_map_chunk_storage.load_chunk_metadata(
            flight_id=safe_flight,
            chunk_id=chunk_id,
        ) or {}
        source = str(sidecar.get("source") or _infer_source_from_chunk_id(chunk_id))
        chunk_counts[source] = chunk_counts.get(source, 0) + 1
        points = _safe_int(sidecar.get("point_count"), 0)
        if points > 0:
            point_counts[source] = point_counts.get(source, 0) + points
        if source == "rgbd_colored" and bool(sidecar.get("has_rgb")):
            rgbd_has_rgb = True

    rgbd_count = chunk_counts.get("rgbd_colored", 0)
    nvblox_count = sum(
        chunk_counts.get(key, 0)
        for key in (
            "nvblox_color",
            "nvblox_esdf",
            "nvblox_tsdf",
            "nvblox_mesh",
            "nvblox_occupancy",
        )
    )
    raw_count = chunk_counts.get("mid360_raw", 0)
    colored_available = rgbd_count > 0 or nvblox_count > 0
    raw_only = raw_count > 0 and not colored_available

    if colored_available and nvblox_count > 0:
        quality = "colored_nvblox"
    elif rgbd_count > 0:
        quality = "colored_rgbd"
    elif raw_only:
        quality = "raw_lidar_only"
    else:
        quality = "empty"

    if require_rgb_for_save() and raw_only:
        quality = "degraded_raw_only"

    localization_quality = "ok" if localization_ok else "degraded"
    quality_evidence = colored_available and (rgbd_count == 0 or rgbd_has_rgb or nvblox_count > 0)

    return LiveMapFlightManifest(
        flight_id=safe_flight,
        generated_at=datetime.now(UTC).isoformat(),
        chunk_counts=chunk_counts,
        point_counts=point_counts,
        rgbd_colored_available=rgbd_count > 0,
        rgbd_has_rgb=rgbd_has_rgb,
        nvblox_available=nvblox_count > 0,
        raw_lidar_only=raw_only,
        localization_ok=localization_ok,
        localization_quality=localization_quality,
        quality_evidence=quality_evidence,
        missing_topics=list(missing_topics or []),
        map_quality=quality,
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
        rgbd_has_rgb=bool(payload.get("rgbd_has_rgb")),
        nvblox_available=bool(payload.get("nvblox_available")),
        raw_lidar_only=bool(payload.get("raw_lidar_only")),
        localization_ok=bool(payload.get("localization_ok", True)),
        localization_quality=str(payload.get("localization_quality") or "ok"),
        quality_evidence=bool(payload.get("quality_evidence")),
        missing_topics=_safe_str_list(payload.get("missing_topics")),
        map_quality=str(payload.get("map_quality") or "unknown"),
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
