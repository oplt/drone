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


@router.get("/sensor-rigs", response_model=Page[WarehouseSensorRigOut])
async def list_sensor_rigs(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> Page[WarehouseSensorRigOut]:
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await repo.list_sensor_rigs(
        db,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
        limit=page_limit + 1,
        offset=page_offset,
    )
    return page_from_offset(
        [sensor_rig_out(row) for row in rows], limit=page_limit, offset=page_offset
    )


@router.post(
    "/sensor-rigs",
    response_model=WarehouseSensorRigOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_sensor_rig(
    payload: WarehouseSensorRigCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseSensorRigOut:
    try:
        row = await repo.create_sensor_rig(
            db,
            owner_id=int(org_user.user.id),
            org_id=org_user.user.org_id,
            name=payload.name,
            camera_model=payload.camera_model,
            stereo_baseline_m=payload.stereo_baseline_m,
            intrinsics_url=payload.intrinsics_url,
            extrinsics_url=payload.extrinsics_url,
            extrinsics_json=payload.extrinsics_json,
            imu_transform_json=payload.imu_transform_json,
            firmware_version=payload.firmware_version,
            isaac_ros_version=payload.isaac_ros_version,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return sensor_rig_out(row)


@router.post("/sensor-rigs/{sensor_rig_id}/calibration", response_model=WarehouseSensorRigOut)
async def update_sensor_rig_calibration(
    sensor_rig_id: int,
    payload: WarehouseSensorRigCalibrationIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseSensorRigOut:
    rig = await repo.get_owned_sensor_rig(
        db,
        sensor_rig_id=sensor_rig_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
    try:
        updated = await repo.update_sensor_rig_calibration(
            db,
            rig=rig,
            calibration_status=payload.calibration_status,
            calibration_hash=payload.calibration_hash,
            intrinsics_url=payload.intrinsics_url,
            extrinsics_url=payload.extrinsics_url,
            extrinsics_json=payload.extrinsics_json,
            imu_transform_json=payload.imu_transform_json,
            calibration_meta=payload.calibration_meta,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return sensor_rig_out(updated)


@router.delete("/sensor-rigs/{sensor_rig_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor_rig(
    sensor_rig_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    rig = await repo.get_owned_sensor_rig(
        db,
        sensor_rig_id=sensor_rig_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
    await repo.delete_sensor_rig(db, rig=rig)
    await db.commit()


@router.get("/sensor-rigs/{sensor_rig_id}/health", response_model=WarehouseSensorRigHealthOut)
async def get_sensor_rig_health(
    sensor_rig_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseSensorRigHealthOut:
    rig = await repo.get_owned_sensor_rig(
        db,
        sensor_rig_id=sensor_rig_id,
        owner_id=int(org_user.user.id),
        org_id=org_user.user.org_id,
        allow_org_access=can_access_org_scope(org_user.user),
    )
    if rig is None:
        raise HTTPException(status_code=404, detail="Warehouse sensor rig not found")
    blockers: list[str] = []
    if rig.calibration_status != "valid":
        blockers.append("Sensor rig calibration is not valid.")
    if not rig.intrinsics_url or not rig.extrinsics_json:
        blockers.append("Sensor rig calibration files are incomplete.")
    try:
        from backend.modules.warehouse.service.sensor_calibration import (
            sensor_calibration_checksum,
        )

        if not rig.extrinsics_json or rig.calibration_hash != sensor_calibration_checksum(
            rig.extrinsics_json
        ):
            blockers.append("Sensor rig extrinsics checksum does not match canonical data.")
    except ValueError:
        blockers.append("Sensor rig extrinsics frame tree is invalid.")
    return WarehouseSensorRigHealthOut(
        sensor_rig=sensor_rig_out(rig),
        perception=WarehousePerceptionOut(
            configured=False,
            reachable=False,
            ready=False,
            status="not_configured",
            detail="Warehouse perception bridge is not configured in this backend.",
            components={},
        ),
        ready=not blockers,
        blockers=blockers,
    )
