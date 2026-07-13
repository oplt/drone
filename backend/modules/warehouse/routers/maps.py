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
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
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
    WarehouseMapSetupVersion,
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


@router.get("/maps", response_model=Page[WarehouseMapOut])
async def list_warehouse_maps(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> Page[WarehouseMapOut]:
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await repo.list_warehouse_maps(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        limit=page_limit + 1,
        offset=page_offset,
    )
    return page_from_offset(
        [map_out(row) for row in rows], limit=page_limit, offset=page_offset
    )


@router.post("/maps", response_model=WarehouseMapOut, status_code=status.HTTP_201_CREATED)
async def create_warehouse_map(
    payload: WarehouseMapCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseMapOut:
    if payload.polygon_local_m is not None:
        polygon = [tuple(point[:2]) for point in payload.polygon_local_m]
    elif payload.width_m is not None and payload.length_m is not None:
        polygon = [
            (0.0, 0.0),
            (float(payload.width_m), 0.0),
            (float(payload.width_m), float(payload.length_m)),
            (0.0, float(payload.length_m)),
        ]
    else:
        raise HTTPException(422, "Provide polygon_local_m or both width_m and length_m")
    try:
        project = (
            await get_default_project(db, org_id=int(org_user.user.org_id))
            if org_user.user.org_id
            else None
        )
        row = await repo.create_warehouse_map(
            db,
            owner_id=int(org_user.user.id),
            org_id=org_user.user.org_id,
            project_id=project.id if project else None,
            warehouse_name=payload.name,
            polygon_local_m=polygon,
        )
        db.add(
            WarehouseMapSetupVersion(
                warehouse_map_id=row.id,
                version=1,
                status="draft",
                polygon_local_json=[list(point) for point in polygon],
                origin_transform_json={
                    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
                alignment_deg=0.0,
                alignment_reference="aisle",
                source="map_create",
                confidence=1.0,
                transform_timestamp=datetime.now(UTC),
                max_transform_age_s=300.0,
                covariance_json=[],
                localization_method="unlocalized_draft",
                scale=1.0,
                scale_calibration_json={},
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return map_out(row)


@router.get("/maps/{warehouse_map_id}", response_model=WarehouseMapOut)
async def get_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMapOut:
    warehouse_map = await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    return map_out(warehouse_map)


@router.delete("/maps/{warehouse_map_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    deleted = await repo.delete_warehouse_map(
        db,
        warehouse_map_id=warehouse_map_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    await db.commit()
