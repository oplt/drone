from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import (
    OrgUser,
    require_mission_exec,
    require_org_user,
    require_org_write,
)
from backend.modules.organizations.service import can_access_org_scope, get_default_project
from backend.modules.warehouse.http_access import (
    EXPLORATION_PROFILE_KEY,
    MISSION_DEFAULTS_KEY,
    get_map_or_404,
    read_warehouse_settings,
    repo,
    settings_repo,
    write_warehouse_setting,
)
from backend.modules.warehouse.http_helpers import (
    asset_out,
    dock_out,
    get_scan_target_or_404,
    get_scanned_map_row_or_404,
    inspection_mission_out,
    inspection_result_out,
    map_out,
    pose,
    quality,
    scan_target_out,
    sensor_rig_out,
    source,
)
from backend.modules.warehouse.http_models import *
from backend.modules.warehouse.schemas import (
    WarehouseInspectionMissionCreate,
    WarehouseInspectionMissionRead,
    WarehouseInspectionResultRead,
    WarehouseMissionDefaultsOut,
    WarehouseScanPoseComputeIn,
    WarehouseScanPoseComputeOut,
    WarehouseScanTargetCreate,
    WarehouseScanTargetImport,
    WarehouseScanTargetPage,
    WarehouseScanTargetRead,
    WarehouseScanTargetUpdate,
    WarehouseStructureExtractIn,
    WarehouseStructureExtractOut,
    WarehouseStructureSummaryOut,
)

from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseDockStation,
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.service.inspection import (
    MockWarehouseScanner,
    build_inspection_waypoints,
    compute_scan_pose,
    order_targets,
)
from backend.modules.warehouse.service.live_map_replay import (
    build_disk_live_map_snapshot,
    resolve_client_flight_id_for_scan_job,
)
from backend.modules.warehouse.service.live_map_stream import WarehouseLiveMapSnapshot
from backend.modules.warehouse.service.mission_launch import start_warehouse_scan_mission
from backend.modules.warehouse.service.preflight_background import (
    get_preflight_run as get_stored_preflight_run,
    remember_preflight_run,
)
from backend.modules.warehouse.service.preflight_cache import (
    clear_preflight_snapshot_cache,
    get_cached_preflight_snapshot,
    store_preflight_snapshot_cache,
)
from backend.modules.warehouse.service.preflight_snapshot import (
    build_preflight_snapshot,
    connect_drone_for_preflight,
)
from backend.modules.warehouse.service.structure_jobs import (
    STRUCTURE_ASSET_TYPE,
    ensure_structure_quality_summary,
    get_extraction_state,
    record_extraction_queued,
    resolve_latest_model_flight,
    warehouse_mapping_worker_ready,
)
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record
from backend.observability.prometheus_metrics import (
    preflight_runs_total,
    warehouse_preflight_refresh_duration_seconds,
    warehouse_preflight_refresh_total,
)

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["warehouse"])

@router.get("/scanned-maps", response_model=list[WarehouseScannedMapOut])
async def list_scanned_maps(
    warehouse_map_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseScannedMapOut]:
    rows = await repo.list_scanned_maps(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        warehouse_map_id=warehouse_map_id,
        limit=limit,
    )
    assets = await repo.list_assets_for_models(
        db, model_ids=[int(model.id) for _job, _map, model in rows]
    )
    by_model: dict[int, list[WarehouseAsset]] = {}
    for asset in assets:
        by_model.setdefault(int(asset.model_id), []).append(asset)
    return [
        WarehouseScannedMapOut(
            job_id=int(job.id),
            model_id=int(model.id),
            model_version=int(model.version),
            warehouse_map_id=int(warehouse_map.id),
            warehouse_name=warehouse_map.name,
            status=job.status,
            progress=int(job.progress or 0),
            error=job.error,
            source=source(job, warehouse_map),
            created_at=job.created_at,
            finished_at=job.finished_at,
            polygon_local_m=repo.polygon_from_local(warehouse_map),
            assets=[asset_out(asset) for asset in by_model.get(int(model.id), [])],
        )
        for job, warehouse_map, model in rows
    ]


@router.get(
    "/scanned-maps/{job_id}/live-map-snapshot",
    response_model=WarehouseLiveMapSnapshot,
)
async def get_scanned_map_live_map_snapshot(
    job_id: int,
    mode: Literal["full", "preview"] = "full",
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLiveMapSnapshot:
    client_flight_id = await resolve_client_flight_id_for_scan_job(
        db,
        job_id=job_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if not client_flight_id:
        raise HTTPException(
            status_code=404,
            detail="No live-map flight id found for this scan result.",
        )

    source_filter = (
        {item.strip() for item in source.split(",") if item.strip()}
        if source
        else None
    )
    disk_snapshot = await asyncio.to_thread(
        build_disk_live_map_snapshot,
        client_flight_id,
        mode=mode,
        sources=source_filter,
    )
    chunk_counts: dict[str, int] = {}
    point_counts: dict[str, int] = {}
    if disk_snapshot.updates:
        for chunk in disk_snapshot.updates[0].changed_chunks:
            layer = str(chunk.layer or chunk.source or "unknown")
            chunk_counts[layer] = chunk_counts.get(layer, 0) + 1
            if chunk.point_count:
                point_counts[layer] = point_counts.get(layer, 0) + int(
                    chunk.point_count
                )
    if disk_snapshot.manifest is not None:
        point_counts = dict(disk_snapshot.manifest.point_counts or point_counts)
        chunk_counts = dict(disk_snapshot.manifest.chunk_counts or chunk_counts)

    logger.info(
        "scanned_map_replay_snapshot scanned_map_id=%s flight_id=%s source=disk_manifest "
        "chunk_counts=%s point_counts=%s status=%s",
        job_id,
        client_flight_id,
        chunk_counts,
        point_counts,
        disk_snapshot.status,
    )
    return disk_snapshot


@router.get("/scanned-maps/{job_id}/quality", response_model=WarehouseScannedMapQualityOut)
async def get_scanned_mapquality(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapQualityOut:
    job, warehouse_map, model = await get_scanned_map_row_or_404(
        db, job_id=job_id, user=org_user.user
    )
    assets = await repo.list_assets_for_models(db, model_ids=[int(model.id)])
    return quality(job, warehouse_map, assets)


@router.post("/scanned-maps/compare", response_model=WarehouseScannedMapCompareOut)
async def compare_scanned_maps(
    payload: WarehouseScannedMapCompareIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapCompareOut:
    baseline = await get_scanned_map_row_or_404(
        db, job_id=payload.baseline_job_id, user=org_user.user
    )
    candidate = await get_scanned_map_row_or_404(
        db, job_id=payload.candidate_job_id, user=org_user.user
    )
    baseline_assets, candidate_assets = await asyncio.gather(
        repo.list_assets_for_models(db, model_ids=[int(baseline[2].id)]),
        repo.list_assets_for_models(db, model_ids=[int(candidate[2].id)]),
    )
    bq = quality(baseline[0], baseline[1], baseline_assets)
    cq = quality(candidate[0], candidate[1], candidate_assets)
    return WarehouseScannedMapCompareOut(
        baseline_job_id=payload.baseline_job_id,
        candidate_job_id=payload.candidate_job_id,
        quality_delta=(
            None
            if bq.quality_score is None or cq.quality_score is None
            else cq.quality_score - bq.quality_score
        ),
        coverage_delta=(
            None
            if bq.coverage_percent is None or cq.coverage_percent is None
            else cq.coverage_percent - bq.coverage_percent
        ),
        drift_delta_m=(
            None
            if bq.drift_estimate_m is None or cq.drift_estimate_m is None
            else cq.drift_estimate_m - bq.drift_estimate_m
        ),
    )


@router.delete("/scanned-maps/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scanned_map(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    deleted = await repo.delete_scanned_map_by_job_id(
        db,
        job_id=job_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse scanned map not found")
    await db.commit()


