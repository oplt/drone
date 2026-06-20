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

from backend.core.database.session import Session, get_db
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
    schedule_preflight_refresh,
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

@router.get("/preflight", response_model=WarehousePreflightOut)
async def get_preflight(
    mission_loaded: bool = False,
    deep: bool = False,
    force: bool = False,
    _fresh_vehicle_probe: bool = False,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehousePreflightOut:
    if not force and not deep:
        cached = await get_cached_preflight_snapshot(
            int(org_user.user.id),
            mission_loaded,
        )
        if cached is not None:
            return cached
    snapshot = await build_preflight_snapshot(
        db,
        user=org_user.user,
        deep=deep,
        force=force,
        mission_loaded=mission_loaded,
        start_bridge=False,
    )
    if not force and not deep:
        await store_preflight_snapshot_cache(
            int(org_user.user.id),
            mission_loaded,
            snapshot,
        )
    return snapshot


@router.post("/preflight/refresh", response_model=WarehousePreflightRefreshOut)
async def refresh_preflight(
    mission_loaded: bool = False,
    deep: bool = False,
    force: bool = False,
    _fresh_vehicle_probe: bool = False,
    org_user: OrgUser = Depends(require_org_user),
) -> WarehousePreflightRefreshOut:
    now = datetime.now(UTC)
    effective_deep = True
    effective_force = True
    run_id = f"warehouse-preflight-{uuid4().hex}"
    run = WarehousePreflightRefreshOut(
        run_id=run_id,
        status="running",
        deep=effective_deep,
        force=effective_force,
        mission_loaded=mission_loaded,
        started_at=now,
    )
    remember_preflight_run(run)
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        start_warehouse_mapping_stack,
    )

    schedule_preflight_refresh(
        run_id=run_id,
        build_snapshot=build_preflight_snapshot,
        connect_drone=connect_drone_for_preflight,
        start_mapping_stack=start_warehouse_mapping_stack,
        db_factory=Session,
        user=org_user.user,
        mission_loaded=mission_loaded,
    )
    return run


@router.get("/preflight/runs/{run_id}", response_model=WarehousePreflightRefreshOut)
async def get_preflight_run(
    run_id: str,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehousePreflightRefreshOut:
    run = get_stored_preflight_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Warehouse preflight run not found")
    return run
