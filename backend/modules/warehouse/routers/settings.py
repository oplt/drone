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

@router.get("/mission-defaults", response_model=WarehouseMissionDefaultsOut)
async def get_mission_defaults(
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMissionDefaultsOut:
    data = await read_warehouse_settings(db)
    defaults = data.get(MISSION_DEFAULTS_KEY)
    return WarehouseMissionDefaultsOut.model_validate(
        defaults if isinstance(defaults, dict) else {}
    )


@router.put("/mission-defaults", response_model=WarehouseMissionDefaultsOut)
async def update_mission_defaults(
    payload: WarehouseMissionDefaultsOut,
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionDefaultsOut:
    await write_warehouse_setting(
        db,
        key=MISSION_DEFAULTS_KEY,
        value=payload.model_dump(mode="json"),
    )
    return payload


@router.get("/exploration-profile", response_model=WarehouseExplorationProfileOut)
async def get_exploration_profile(
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseExplorationProfileOut:
    data = await read_warehouse_settings(db)
    profile = data.get(EXPLORATION_PROFILE_KEY)
    return WarehouseExplorationProfileOut.model_validate(
        profile if isinstance(profile, dict) else {}
    )


@router.put("/exploration-profile", response_model=WarehouseExplorationProfileOut)
async def update_exploration_profile(
    payload: WarehouseExplorationProfileOut,
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseExplorationProfileOut:
    await write_warehouse_setting(
        db,
        key=EXPLORATION_PROFILE_KEY,
        value=payload.model_dump(mode="json"),
    )
    return payload


