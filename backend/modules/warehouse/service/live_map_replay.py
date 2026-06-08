from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.missions.runtime_models import MissionRuntime
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.service.live_map_storage import warehouse_live_map_chunk_storage
from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveHealthFlags,
    WarehouseLiveMapSnapshot,
    WarehouseLiveMapUpdate,
    WarehouseLiveVoxelChunk,
)

_CHUNK_ID_RE = re.compile(r"^(.+)-[0-9a-f]{16}\.[a-z0-9]+$", re.IGNORECASE)
_PREVIEW_CHUNK_ID_RE = re.compile(r"^(.+)-[0-9a-f]{16}\.preview\.json$", re.IGNORECASE)


def _chunk_id_from_filename(path: Path) -> str:
    preview_match = _PREVIEW_CHUNK_ID_RE.match(path.name)
    if preview_match:
        return preview_match.group(1)
    match = _CHUNK_ID_RE.match(path.name)
    if match:
        return match.group(1)
    return path.stem.split("-", 1)[0]


def _load_preview_chunk(path: Path, *, sequence: int) -> WarehouseLiveVoxelChunk | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    preview_points = payload.get("preview_points_m")
    if not isinstance(preview_points, list) or not preview_points:
        return None
    chunk_id = _chunk_id_from_filename(path)
    bbox = payload.get("bbox_local_m")
    return WarehouseLiveVoxelChunk(
        id=chunk_id,
        kind="point_cloud",
        sequence=int(payload.get("sequence", sequence)),
        point_count=payload.get("point_count"),
        byte_size=path.stat().st_size,
        bbox_local_m=bbox if isinstance(bbox, list) and len(bbox) == 6 else None,
        preview_points_m=preview_points,
    )


def build_disk_live_map_snapshot(client_flight_id: str) -> WarehouseLiveMapSnapshot:
    safe_flight = client_flight_id.strip()
    root = (warehouse_live_map_chunk_storage.root / safe_flight).resolve()
    if not root.exists() or not root.is_dir():
        return WarehouseLiveMapSnapshot(
            flight_id=client_flight_id,
            status="empty",
            last_update_at=None,
            updates=[],
        )

    changed_chunks: list[WarehouseLiveVoxelChunk] = []
    latest_mtime = 0.0
    for sequence, path in enumerate(sorted(root.iterdir(), key=lambda item: item.name)):
        if not path.is_file():
            continue
        latest_mtime = max(latest_mtime, path.stat().st_mtime)
        if path.suffix.lower() == ".json" and path.name.endswith(".preview.json"):
            preview_chunk = _load_preview_chunk(path, sequence=sequence)
            if preview_chunk is not None:
                changed_chunks.append(preview_chunk)
            continue

        chunk_id = _chunk_id_from_filename(path)
        stored = warehouse_live_map_chunk_storage.resolve(
            flight_id=client_flight_id,
            chunk_id=chunk_id,
        )
        if stored is None:
            continue
        kind = "point_cloud" if path.suffix.lower() == ".xyz32" else "mesh"
        changed_chunks.append(
            WarehouseLiveVoxelChunk(
                id=stored.chunk_id,
                kind=kind,
                url=stored.url,
                content_type=stored.content_type,
                byte_size=stored.byte_size,
                checksum_sha256=stored.checksum_sha256,
                sequence=sequence,
            )
        )

    if not changed_chunks:
        return WarehouseLiveMapSnapshot(
            flight_id=client_flight_id,
            status="empty",
            last_update_at=None,
            updates=[],
        )

    changed_chunks.sort(key=lambda chunk: chunk.sequence)
    timestamp = datetime.fromtimestamp(latest_mtime, tz=UTC)
    update = WarehouseLiveMapUpdate(
        flight_id=client_flight_id,
        timestamp=timestamp,
        changed_chunks=changed_chunks,
        health=WarehouseLiveHealthFlags(
            missing_mesh=True,
            missing_point_cloud=False,
            nvblox_ready=True,
            mapping_recording=False,
            stack_running=False,
        ),
    )
    return WarehouseLiveMapSnapshot(
        flight_id=client_flight_id,
        status="finalized",
        last_update_at=timestamp,
        updates=[update],
    )


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
    for job, _warehouse_map, model in rows:
        if int(job.id) != int(job_id):
            continue
        assets = await repo.list_assets_for_models(db, model_ids=[int(model.id)])
        for asset in assets:
            capture = (asset.meta_data or {}).get("capture_result") or {}
            raw_flight_id = capture.get("flight_id")
            if raw_flight_id is None:
                continue
            try:
                db_flight_id = int(raw_flight_id)
            except (TypeError, ValueError):
                token = str(raw_flight_id).strip()
                return token or None
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
