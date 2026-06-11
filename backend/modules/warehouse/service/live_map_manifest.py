from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.modules.warehouse.service.live_map_config import require_rgb_for_save
from backend.modules.warehouse.service.live_map_storage import warehouse_live_map_chunk_storage

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "live_map_manifest.json"
_CHUNK_ID_RE = re.compile(
    r"^(rgbd|mid360|nvblox_color|nvblox_esdf|nvblox_tsdf|nvblox_mesh)_"
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


def _infer_source_from_chunk_id(chunk_id: str) -> str:
    lower = chunk_id.lower()
    if lower.startswith("rgbd_"):
        return "rgbd_colored"
    if lower.startswith("mid360_"):
        return "mid360_raw"
    if lower.startswith("nvblox_color_"):
        return "nvblox_color"
    if lower.startswith("nvblox_esdf_"):
        return "nvblox_esdf"
    if lower.startswith("nvblox_tsdf_"):
        return "nvblox_tsdf"
    if lower.startswith("nvblox_mesh_"):
        return "nvblox_mesh"
    return "unknown"


def build_manifest_from_flight_dir(
    flight_id: str,
    *,
    missing_topics: list[str] | None = None,
    localization_ok: bool = True,
    diagnostics_phase: str = "pre_finalize",
) -> LiveMapFlightManifest:
    root = (warehouse_live_map_chunk_storage.root / flight_id.strip()).resolve()
    chunk_counts: dict[str, int] = {}
    point_counts: dict[str, int] = {}
    seen_ids: set[str] = set()
    rgbd_has_rgb = False

    if root.exists():
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith(".meta.json") or name.endswith(".uploading"):
                continue
            if name.endswith(".preview.json"):
                continue
            if not _CHUNK_ID_RE.match(path.stem.split("-", 1)[0]):
                continue

            chunk_id = path.stem.split("-", 1)[0]
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)

            sidecar = warehouse_live_map_chunk_storage.load_chunk_metadata(
                flight_id=flight_id,
                chunk_id=chunk_id,
            ) or {}
            source = str(sidecar.get("source") or _infer_source_from_chunk_id(chunk_id))
            chunk_counts[source] = chunk_counts.get(source, 0) + 1
            points = int(sidecar.get("point_count") or 0)
            if points > 0:
                point_counts[source] = point_counts.get(source, 0) + points
            if source == "rgbd_colored" and sidecar.get("has_rgb"):
                rgbd_has_rgb = True

    rgbd_count = chunk_counts.get("rgbd_colored", 0)
    nvblox_count = sum(
        chunk_counts.get(key, 0)
        for key in ("nvblox_color", "nvblox_esdf", "nvblox_tsdf", "nvblox_mesh")
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
        flight_id=flight_id,
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
    root = warehouse_live_map_chunk_storage.root / manifest.flight_id.strip()
    root.mkdir(parents=True, exist_ok=True)
    path = root / _MANIFEST_NAME
    path.write_text(
        json.dumps(manifest.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_flight_manifest(flight_id: str) -> LiveMapFlightManifest | None:
    path = warehouse_live_map_chunk_storage.root / flight_id.strip() / _MANIFEST_NAME
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return LiveMapFlightManifest(
        flight_id=str(payload.get("flight_id") or flight_id),
        generated_at=str(payload.get("generated_at") or ""),
        chunk_counts=dict(payload.get("chunk_counts") or {}),
        point_counts=dict(payload.get("point_counts") or {}),
        rgbd_colored_available=bool(payload.get("rgbd_colored_available")),
        rgbd_has_rgb=bool(payload.get("rgbd_has_rgb")),
        nvblox_available=bool(payload.get("nvblox_available")),
        raw_lidar_only=bool(payload.get("raw_lidar_only")),
        localization_ok=bool(payload.get("localization_ok", True)),
        localization_quality=str(payload.get("localization_quality") or "ok"),
        quality_evidence=bool(payload.get("quality_evidence")),
        missing_topics=list(payload.get("missing_topics") or []),
        map_quality=str(payload.get("map_quality") or "unknown"),
        diagnostics_phase=str(payload.get("diagnostics_phase") or "unknown"),
        manifest_status=str(payload.get("manifest_status") or "complete"),
        missing_chunks=list(payload.get("missing_chunks") or []),
        total_bytes=int(payload.get("total_bytes") or 0),
    )


def validate_manifest_chunk_files(
    flight_id: str,
    *,
    chunk_ids: list[str] | None = None,
) -> tuple[list[str], int]:
    """Return missing chunk ids and total on-disk bytes for resolved chunks."""
    missing: list[str] = []
    total_bytes = 0
    root = (warehouse_live_map_chunk_storage.root / flight_id.strip()).resolve()
    if chunk_ids is None:
        chunk_ids = []
        if root.exists():
            seen: set[str] = set()
            for path in sorted(root.iterdir()):
                if not path.is_file():
                    continue
                name = path.name.lower()
                if name.endswith(".meta.json") or name.endswith(".uploading"):
                    continue
                if name.endswith(".preview.json"):
                    continue
                if not _CHUNK_ID_RE.match(path.stem.split("-", 1)[0]):
                    continue
                chunk_id = path.stem.split("-", 1)[0]
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                chunk_ids.append(chunk_id)

    for chunk_id in chunk_ids:
        stored = warehouse_live_map_chunk_storage.resolve(
            flight_id=flight_id,
            chunk_id=chunk_id,
        )
        if stored is None:
            missing.append(chunk_id)
            continue
        total_bytes += int(stored.byte_size)
    return missing, total_bytes


def finalize_manifest_integrity(manifest: LiveMapFlightManifest) -> LiveMapFlightManifest:
    missing, total_bytes = validate_manifest_chunk_files(manifest.flight_id)
    manifest.missing_chunks = missing
    manifest.total_bytes = total_bytes
    if missing:
        manifest.manifest_status = "partial"
        logger.warning(
            "live_map_manifest_partial flight_id=%s missing_chunks=%s total_bytes=%s "
            "chunk_counts=%s point_counts=%s",
            manifest.flight_id,
            missing,
            total_bytes,
            manifest.chunk_counts,
            manifest.point_counts,
        )
    else:
        manifest.manifest_status = "complete"
        logger.info(
            "live_map_manifest_finalized flight_id=%s chunk_counts=%s point_counts=%s "
            "total_bytes=%s",
            manifest.flight_id,
            manifest.chunk_counts,
            manifest.point_counts,
            total_bytes,
        )
    return manifest


def validate_save_quality(manifest: LiveMapFlightManifest) -> tuple[bool, str]:
    if manifest.map_quality == "empty":
        return False, "No live-map chunks were persisted for this flight."
    if require_rgb_for_save() and manifest.raw_lidar_only:
        return False, (
            "Map save degraded: only raw Mid360 LiDAR chunks exist; "
            "RGB-D or nvBlox colored data is required."
        )
    if manifest.raw_lidar_only:
        return True, "Saved map contains raw LiDAR only (debug/fallback)."
    if manifest.manifest_status == "partial":
        return (
            False,
            f"Live-map manifest is partial; missing {len(manifest.missing_chunks)} chunk file(s).",
        )
    return True, "Saved map contains colored RGB-D and/or nvBlox layers."
