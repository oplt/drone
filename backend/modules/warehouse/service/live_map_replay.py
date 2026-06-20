from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.missions.runtime_models import MissionRuntime
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest
from backend.modules.warehouse.service.live_map_snapshot_cache import (
    disk_live_map_snapshot_cache,
)
from backend.modules.warehouse.service.live_map_storage import warehouse_live_map_chunk_storage
from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveHealthFlags,
    WarehouseLiveMapManifestSummary,
    WarehouseLiveMapSnapshot,
    WarehouseLiveMapUpdate,
    WarehouseLiveVoxelChunk,
)

logger = logging.getLogger(__name__)

_CHUNK_ID_RE = re.compile(r"^(.+)-[0-9a-f]{16}\.[a-z0-9]+$", re.IGNORECASE)
_PREVIEW_CHUNK_ID_RE = re.compile(r"^(.+)-[0-9a-f]{16}\.preview\.json$", re.IGNORECASE)
_META_CHUNK_ID_RE = re.compile(r"^(.+)\.meta\.json$", re.IGNORECASE)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_sequence(value: Any, fallback: int) -> int:
    return max(0, _safe_int(value, fallback))


def _safe_flight_root(client_flight_id: str) -> Path:
    if hasattr(warehouse_live_map_chunk_storage, "flight_dir"):
        return warehouse_live_map_chunk_storage.flight_dir(client_flight_id)  # type: ignore[attr-defined]
    return (warehouse_live_map_chunk_storage.root / client_flight_id.strip()).resolve()


def _chunk_id_from_filename(path: Path) -> str:
    preview_match = _PREVIEW_CHUNK_ID_RE.match(path.name)
    if preview_match:
        return preview_match.group(1)
    meta_match = _META_CHUNK_ID_RE.match(path.name)
    if meta_match:
        return meta_match.group(1).rsplit("-", 1)[0]
    match = _CHUNK_ID_RE.match(path.name)
    if match:
        return match.group(1)
    return path.stem.rsplit("-", 1)[0]


def _infer_chunk_metadata(chunk_id: str, path: Path) -> dict[str, Any]:
    """Infer replay metadata from chunk id prefix and on-disk file extension."""
    suffix = path.suffix.lower()
    lower_id = chunk_id.lower()

    source: str | None = None
    layer: str | None = None
    kind: str = "point_cloud"
    encoding: str | None = None
    has_rgb = False

    if lower_id.startswith("rgbd_xyz_"):
        source = "rgbd_xyz_uncolored"
        layer = "rgbd_xyz_uncolored"
    elif lower_id.startswith(("rgbd_colored_", "rgbd_")):
        source = "rgbd_colored"
        layer = "rgbd_colored"
    elif lower_id.startswith(("mid360_raw_", "mid360_")):
        source = "mid360_raw"
        layer = "mid360_lidar"
    elif lower_id.startswith("nvblox_color_"):
        source = "nvblox_color"
        layer = "nvblox_color"
    elif lower_id.startswith("nvblox_esdf_"):
        source = "nvblox_esdf"
        layer = "nvblox_esdf"
        kind = "esdf"
    elif lower_id.startswith("nvblox_tsdf_"):
        source = "nvblox_tsdf"
        layer = "nvblox_tsdf"
    elif lower_id.startswith("nvblox_mesh_"):
        source = "nvblox_mesh"
        layer = "nvblox_mesh"
        kind = "mesh"
    elif lower_id.startswith("nvblox_occupancy_"):
        source = "nvblox_occupancy"
        layer = "nvblox_occupancy"
        kind = "occupancy"

    if suffix == ".xyzrgb32":
        kind = "point_cloud"
        encoding = "xyzrgb32_v1"
        has_rgb = True
    elif suffix == ".xyz32":
        kind = "point_cloud"
        encoding = "xyz32_v1"
        has_rgb = False
    elif suffix == ".glb":
        kind = "mesh"
        encoding = None
    elif suffix == ".vox":
        kind = "esdf" if lower_id.startswith("nvblox_esdf_") else "occupancy"
    elif suffix == ".grid":
        kind = "occupancy" if lower_id.startswith("nvblox_occupancy_") else "costmap"

    metadata: dict[str, Any] = {
        "kind": kind,
        "source": source,
        "layer": layer,
        "encoding": encoding,
        "has_rgb": has_rgb,
    }

    sequence_match = re.search(r"_(\d+)$", chunk_id)
    if sequence_match:
        metadata["sequence"] = int(sequence_match.group(1))

    return metadata


def _merge_chunk_metadata(
    *,
    chunk_id: str,
    stored_path: Path,
    sidecar: dict[str, Any] | None,
) -> dict[str, Any]:
    inferred = _infer_chunk_metadata(chunk_id, stored_path)
    if not sidecar:
        return inferred
    merged = dict(inferred)
    for key, value in sidecar.items():
        if value is not None:
            merged[key] = value
    if merged.get("source") == "rgbd_colored" and merged.get("has_rgb") is not True:
        merged["source"] = "rgbd_xyz_uncolored"
        merged["layer"] = "rgbd_xyz_uncolored"
        merged["layer_type"] = "rgbd_xyz_uncolored"
    return merged


def _load_preview_chunk(
    path: Path, *, sequence: int, sources: set[str] | None = None
) -> WarehouseLiveVoxelChunk | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stat = path.stat()
    except (OSError, json.JSONDecodeError):
        logger.debug("Could not load live-map preview chunk path=%s", path, exc_info=True)
        return None
    if not isinstance(payload, dict):
        return None
    preview_points = payload.get("preview_points_m")
    if not isinstance(preview_points, list) or not preview_points:
        return None
    chunk_id = _chunk_id_from_filename(path)
    bbox = payload.get("bbox_local_m")
    metadata = _infer_chunk_metadata(chunk_id, path)
    source = metadata.get("source")
    if sources is not None and str(source or "unknown") not in sources:
        return None
    return WarehouseLiveVoxelChunk(
        id=chunk_id,
        kind="point_cloud",
        sequence=_safe_sequence(
            payload.get("sequence", metadata.get("sequence", sequence)), sequence
        ),
        point_count=payload.get("point_count"),
        byte_size=stat.st_size,
        bbox_local_m=bbox if isinstance(bbox, list) and len(bbox) == 6 else None,
        preview_points_m=preview_points,
        source=source,
        layer=metadata.get("layer"),
        has_rgb=metadata.get("has_rgb"),
        fields=metadata.get("fields") if isinstance(metadata.get("fields"), list) else [],
        source_topic=metadata.get("source_topic"),
        cloud_age_ms=metadata.get("cloud_age_ms"),
        transform_age_ms=metadata.get("transform_age_ms"),
        encoding=metadata.get("encoding"),
    )


def _chunk_from_metadata(
    *,
    stored,
    metadata: dict[str, Any],
    fallback_sequence: int,
) -> WarehouseLiveVoxelChunk:
    raw_kind = str(metadata.get("kind") or "point_cloud")
    allowed = {"mesh", "point_cloud", "occupancy", "esdf", "costmap"}
    kind = raw_kind if raw_kind in allowed else "point_cloud"
    return WarehouseLiveVoxelChunk(
        id=stored.chunk_id,
        kind=kind,  # type: ignore[arg-type]
        url=stored.url,
        content_type=str(metadata.get("content_type") or stored.content_type),
        byte_size=stored.byte_size,
        checksum_sha256=stored.checksum_sha256,
        sequence=_safe_sequence(metadata.get("sequence", fallback_sequence), fallback_sequence),
        point_count=metadata.get("point_count"),
        bbox_local_m=metadata.get("bbox_local_m")
        if isinstance(metadata.get("bbox_local_m"), list)
        else None,
        source=metadata.get("source"),
        layer=metadata.get("layer"),
        layer_type=metadata.get("layer_type") or metadata.get("layer"),
        has_rgb=metadata.get("has_rgb"),
        encoding=metadata.get("encoding"),
        frame_id=metadata.get("frame_id"),
        stamp=metadata.get("stamp"),
        priority=metadata.get("priority"),
    )


def _iter_preview_paths(root: Path) -> Iterable[Path]:
    for path in sorted(root.glob("*.preview.json"), key=lambda item: item.name):
        if path.is_file():
            yield path


def _iter_stored_chunks(client_flight_id: str) -> list[Any]:
    if hasattr(warehouse_live_map_chunk_storage, "iter_chunk_files"):
        return list(warehouse_live_map_chunk_storage.iter_chunk_files(flight_id=client_flight_id))  # type: ignore[attr-defined]
    root = _safe_flight_root(client_flight_id)
    if not root.exists() or not root.is_dir():
        return []
    seen: set[str] = set()
    stored_items: list[Any] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        name = path.name.lower()
        if (
            name.endswith(".meta.json")
            or name.endswith(".uploading")
            or name.endswith(".preview.json")
        ):
            continue
        chunk_id = _chunk_id_from_filename(path)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        stored = warehouse_live_map_chunk_storage.resolve(
            flight_id=client_flight_id, chunk_id=chunk_id
        )
        if stored is not None:
            stored_items.append(stored)
    return stored_items


def _build_disk_live_map_snapshot_uncached(
    client_flight_id: str,
    *,
    mode: str = "full",
    sources: set[str] | None = None,
) -> WarehouseLiveMapSnapshot:
    safe_flight = str(client_flight_id or "").strip()
    root = _safe_flight_root(safe_flight)
    if not root.exists() or not root.is_dir():
        return WarehouseLiveMapSnapshot(
            flight_id=client_flight_id,
            status="empty",
            last_update_at=None,
            updates=[],
        )

    changed_chunks: list[WarehouseLiveVoxelChunk] = []
    latest_mtime = 0.0
    seen_chunk_ids: set[str] = set()
    sequence = 0

    for path in _iter_preview_paths(root):
        try:
            latest_mtime = max(latest_mtime, path.stat().st_mtime)
        except OSError:
            continue
        preview_chunk = _load_preview_chunk(path, sequence=sequence, sources=sources)
        sequence += 1
        if preview_chunk is not None and preview_chunk.id not in seen_chunk_ids:
            changed_chunks.append(preview_chunk)
            seen_chunk_ids.add(preview_chunk.id)

    for stored in _iter_stored_chunks(safe_flight):
        chunk_id = str(stored.chunk_id)
        if chunk_id in seen_chunk_ids:
            continue
        with suppress(OSError):
            latest_mtime = max(latest_mtime, stored.path.stat().st_mtime)

        sidecar = warehouse_live_map_chunk_storage.load_chunk_metadata(
            flight_id=safe_flight,
            chunk_id=chunk_id,
        )
        metadata = _merge_chunk_metadata(
            chunk_id=chunk_id,
            stored_path=stored.path,
            sidecar=sidecar,
        )

        chunk_source = str(metadata.get("source") or "unknown")
        if sources is not None and chunk_source not in sources:
            continue

        chunk = _chunk_from_metadata(
            stored=stored,
            metadata=metadata,
            fallback_sequence=sequence,
        )
        sequence += 1
        changed_chunks.append(chunk)
        seen_chunk_ids.add(chunk_id)

    if mode == "preview" and changed_chunks:
        preview_by_source: dict[str, WarehouseLiveVoxelChunk] = {}
        for chunk in changed_chunks:
            source_key = str(chunk.source or "unknown")
            existing = preview_by_source.get(source_key)
            if existing is None or (chunk.sequence or 0) >= (existing.sequence or 0):
                preview_by_source[source_key] = chunk
        changed_chunks = list(preview_by_source.values())

    if not changed_chunks:
        return WarehouseLiveMapSnapshot(
            flight_id=client_flight_id,
            status="empty",
            last_update_at=None,
            updates=[],
        )

    changed_chunks.sort(
        key=lambda chunk: (
            chunk.priority if chunk.priority is not None else 50,
            chunk.layer or "",
            chunk.sequence,
            chunk.id,
        )
    )
    timestamp = datetime.fromtimestamp(latest_mtime or datetime.now(UTC).timestamp(), tz=UTC)
    manifest_model = load_flight_manifest(safe_flight)
    manifest_summary = None
    if manifest_model is not None:
        manifest_summary = WarehouseLiveMapManifestSummary(
            map_quality=manifest_model.map_quality,
            rgbd_colored_available=manifest_model.rgbd_colored_available,
            rgbd_cloud_available=manifest_model.rgbd_cloud_available,
            rgbd_has_rgb=manifest_model.rgbd_has_rgb,
            default_view_layer=manifest_model.default_view_layer,
            diagnostic_nvblox_layers=list(manifest_model.diagnostic_nvblox_layers),
            nvblox_available=manifest_model.nvblox_available,
            raw_lidar_only=manifest_model.raw_lidar_only,
            chunk_counts=dict(manifest_model.chunk_counts),
            point_counts=dict(manifest_model.point_counts),
            missing_topics=list(manifest_model.missing_topics),
        )
    update = WarehouseLiveMapUpdate(
        flight_id=client_flight_id,
        timestamp=timestamp,
        changed_chunks=changed_chunks,
        health=WarehouseLiveHealthFlags(
            missing_mesh=True,
            missing_point_cloud=False,
            mapping_recording=False,
            stack_running=False,
        ),
    )
    return WarehouseLiveMapSnapshot(
        flight_id=client_flight_id,
        status="finalized",
        last_update_at=timestamp,
        updates=[update],
        manifest=manifest_summary,
    )


def build_disk_live_map_snapshot(
    client_flight_id: str,
    *,
    mode: str = "full",
    sources: set[str] | None = None,
) -> WarehouseLiveMapSnapshot:
    from backend.core.config.runtime import settings

    safe_flight = str(client_flight_id or "").strip()
    root = _safe_flight_root(safe_flight)
    signature = disk_live_map_snapshot_cache.signature(root)
    if signature is None:
        return _build_disk_live_map_snapshot_uncached(
            client_flight_id,
            mode=mode,
            sources=sources,
        )

    key = (str(root), mode, tuple(sorted(sources or ())))
    ttl_s = max(
        0.0,
        float(getattr(settings, "warehouse_live_map_snapshot_cache_ttl_s", 120.0)),
    )
    cached = disk_live_map_snapshot_cache.get(
        key,
        signature=signature,
        ttl_s=ttl_s,
    )
    if cached is not None:
        return cached

    snapshot = _build_disk_live_map_snapshot_uncached(
        client_flight_id,
        mode=mode,
        sources=sources,
    )
    disk_live_map_snapshot_cache.put(key, signature=signature, snapshot=snapshot)
    return snapshot


def _extract_capture_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        capture = value.get("capture_result")
        return capture if isinstance(capture, dict) else {}
    return {}


def _clean_token(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip()
    return token or None


async def resolve_client_flight_id_for_scan_job(
    db: AsyncSession,
    *,
    job_id: int,
    owner_id: int,
    org_id: int | None,
    allow_org_access: bool,
) -> str | None:
    repo = WarehouseMappingRepository()
    rows = await repo.list_scanned_maps(
        db,
        owner_id=owner_id,
        org_id=org_id,
        allow_org_access=allow_org_access,
        warehouse_map_id=None,
        limit=200,
    )
    target_job_id = int(job_id)
    for job, _warehouse_map, model in rows:
        try:
            current_job_id = int(job.id)
        except (TypeError, ValueError):
            continue
        if current_job_id != target_job_id:
            continue

        capture = _extract_capture_dict(job.params if isinstance(job.params, dict) else {})
        token = _clean_token(capture.get("client_flight_id"))
        if token:
            return token

        assets = await repo.list_assets_for_models(db, model_ids=[int(model.id)])
        for asset in assets:
            asset_meta = asset.meta_data if isinstance(asset.meta_data, dict) else {}
            capture = _extract_capture_dict(asset_meta)
            token = _clean_token(capture.get("client_flight_id"))
            if token:
                return token

            raw_flight_id = capture.get("flight_id")
            if raw_flight_id is None:
                continue
            try:
                db_flight_id = int(raw_flight_id)
            except (TypeError, ValueError):
                return _clean_token(raw_flight_id)
            runtime = (
                await db.execute(
                    select(MissionRuntime.client_flight_id)
                    .where(MissionRuntime.flight_id == db_flight_id)
                    .order_by(MissionRuntime.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if runtime:
                return str(runtime)
        break
    return None
