"""Live-map flight manifest — integrity and save-quality validation."""

from __future__ import annotations

import logging

from .deps import resolve, resolve_chunk_storage
from .models import LiveMapFlightManifest
from .storage_access import _iter_stored_chunks

logger = logging.getLogger(__name__)


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
    storage = resolve_chunk_storage()
    for raw_chunk_id in chunk_ids:
        chunk_id = str(raw_chunk_id or "").strip()
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        stored = storage.resolve(
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
    if resolve("require_rgb_for_save")() and manifest.raw_lidar_only:
        return False, (
            "Map save degraded: only raw Mid360 LiDAR chunks exist; "
            "RGB-D or nvBlox colored data is required."
        )
    if manifest.raw_lidar_only:
        return True, "Saved map contains raw LiDAR only (debug/fallback)."
    return True, "Saved map contains colored RGB-D and/or nvBlox layers."


__all__ = [
    "finalize_manifest_integrity",
    "validate_manifest_chunk_files",
    "validate_save_quality",
]
