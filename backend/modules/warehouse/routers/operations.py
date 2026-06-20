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
from backend.modules.missions.schemas.mission_create import MissionCreateOut
from backend.modules.missions.service.mission_builder import build_mission
from backend.modules.preflight.checks.schemas import CheckStatus
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
from backend.modules.warehouse.service.mission_launch import (
    build_warehouse_scan_mission_payload,
    start_warehouse_scan_mission,
)
from backend.modules.warehouse.service.warehouse_preflight import (
    run_warehouse_ros_preflight_report,
    warehouse_preflight_can_start,
    warehouse_preflight_failed_checks,
)
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

@router.get("/mapping-stack/status", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_status(
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        get_mapping_stack_status,
    )

    status = await get_mapping_stack_status()
    log_parser = status.nvblox_health.get("log_parser")
    warning = (
        log_parser.get("warning")
        if isinstance(log_parser, dict)
        else None
    )
    return WarehouseMappingStackStatusOut(
        running=status.running,
        pid=status.pid,
        started_at=status.started_at,
        last_exit_code=status.last_exit_code,
        nvblox_running=status.nvblox_running,
        phase=status.phase,
        last_error=status.last_error,
        warning=str(warning) if warning else None,
    )


@router.post("/mapping-stack/start", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_start(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        start_warehouse_mapping_stack,
    )

    status = await start_warehouse_mapping_stack()
    log_parser = status.nvblox_health.get("log_parser")
    warning = (
        log_parser.get("warning")
        if isinstance(log_parser, dict)
        else None
    )
    return WarehouseMappingStackStatusOut(
        running=status.running,
        pid=status.pid,
        started_at=status.started_at,
        last_exit_code=status.last_exit_code,
        nvblox_running=status.nvblox_running,
        phase=status.phase,
        last_error=status.last_error,
        warning=str(warning) if warning else None,
    )


@router.post("/mapping-stack/stop", response_model=WarehouseMappingStackStatusOut)
async def mapping_stack_stop(
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMappingStackStatusOut:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        get_mapping_stack_status,
        shutdown_warehouse_mapping_stack,
    )

    await shutdown_warehouse_mapping_stack()
    status = await get_mapping_stack_status()
    return WarehouseMappingStackStatusOut(
        running=status.running,
        pid=status.pid,
        started_at=status.started_at,
        last_exit_code=status.last_exit_code,
        nvblox_running=status.nvblox_running,
        phase=status.phase,
        last_error=status.last_error,
    )


@router.post("/manual-mapping/start", response_model=WarehouseCommandOut)
async def manual_mapping_start(
    _payload: dict[str, Any],
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseCommandOut:
    return WarehouseCommandOut(
        accepted=False,
        status="not_configured",
        detail="Warehouse manual mapping bridge is not configured in this backend.",
    )


@router.post("/manual-mapping/stop", response_model=WarehouseCommandOut)
async def manual_mapping_stop(
    _payload: dict[str, Any],
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseCommandOut:
    return WarehouseCommandOut(accepted=True, status="stopped")


@router.post("/missions/start", response_model=WarehouseMissionLaunchOut)
async def mission_start(
    payload: WarehouseMissionStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionLaunchOut:
    warehouse_map, mission_payload, base_height_m = await build_warehouse_scan_mission_payload(
        db,
        user=org_user.user,
        warehouse_map_id=payload.warehouse_map_id,
        mission_name=payload.mission_name,
        sensor_rig_id=payload.sensor_rig_id,
        dock_id=payload.dock_id,
        reference_mapping_job_id=payload.reference_mapping_job_id,
    )
    mission, _ = build_mission(mission_payload, owner_id=int(org_user.user.id))
    preflight_report = await run_warehouse_ros_preflight_report(
        mission.get_preflight_mission_data(),
        cruise_alt=base_height_m,
        force=True,
        source="mission_start",
    )
    preflight_status = str(preflight_report.overall_status)
    if not warehouse_preflight_can_start(preflight_report):
        failed_checks = warehouse_preflight_failed_checks(preflight_report)
        raise HTTPException(
            status_code=412,
            detail={
                "message": (
                    "Warehouse ROS preflight failed before mission start."
                    + (f" Failed checks: {', '.join(failed_checks)}" if failed_checks else "")
                ),
                "overall_status": preflight_status,
                "blocking_reasons": failed_checks,
                "preflight": {
                    "preflight_run_id": "",
                    "overall_status": preflight_status,
                    "can_start_mission": False,
                },
            },
        )
    launch = await start_warehouse_scan_mission(
        db=db,
        user=org_user.user,
        warehouse_map_id=payload.warehouse_map_id,
        mission_name=payload.mission_name,
        sensor_rig_id=payload.sensor_rig_id,
        dock_id=payload.dock_id,
        reference_mapping_job_id=payload.reference_mapping_job_id,
    )
    return WarehouseMissionLaunchOut(
        warehouse_map_id=int(warehouse_map.id),
        warehouse_name=warehouse_map.name,
        preflight=WarehouseMissionLaunchPreflightOut(
            preflight_run_id=str(launch.get("preflight_run_id") or ""),
            overall_status=preflight_status,
            can_start_mission=preflight_report.overall_status != CheckStatus.FAIL,
        ),
        mission=MissionCreateOut.model_validate(launch),
    )


@router.post("/missions/exploration/start", response_model=WarehouseCommandOut)
async def exploration_start(
    payload: WarehouseExplorationStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseCommandOut:
    await get_map_or_404(db, warehouse_map_id=payload.warehouse_map_id, user=org_user.user)
    raise HTTPException(
        status_code=503,
        detail="Warehouse exploration launcher is not configured in this backend.",
    )
