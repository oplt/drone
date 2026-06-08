from __future__ import annotations

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


def _chunk_id_from_filename(path: Path) -> str:
    match = _CHUNK_ID_RE.match(path.name)
    if match:
        return match.group(1)
    return path.stem.split("-", 1)[0]


def build_disk_live_map_snapshot(client_flight_id: str) -> WarehouseLiveMapSnapshot:
    root = (warehouse_live_map_chunk_storage.root / client_flight_id).resolve()
    if not root.exists() or not root.is_dir():
        return WarehouseLiveMapSnapshot(
            flight_id=client_flight_id,
            status="empty",
            last_update_at=None,
            updates=[],
        )

    changed_chunks: list[WarehouseLiveVoxelChunk] = []
    for sequence, path in enumerate(sorted(root.iterdir())):
        if not path.is_file():
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

    timestamp = datetime.fromtimestamp(
        max(path.stat().st_mtime for path in root.iterdir() if path.is_file()),
        tz=UTC,
    )
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
