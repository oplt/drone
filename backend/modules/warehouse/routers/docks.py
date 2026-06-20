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

@router.get("/maps/{warehouse_map_id}/docks", response_model=list[WarehouseDockOut])
async def list_warehouse_docks(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseDockOut]:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = await repo.list_dock_stations(db, warehouse_map_id=warehouse_map_id)
    return [dock_out(row) for row in rows]


@router.post(
    "/maps/{warehouse_map_id}/docks",
    response_model=WarehouseDockOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_dock(
    warehouse_map_id: int,
    payload: WarehouseDockCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseDockOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    try:
        row = await repo.create_dock_station(
            db,
            warehouse_map_id=warehouse_map_id,
            name=payload.name,
            pose_local_json=payload.pose.model_dump(),
            entrypose_local_json=payload.entrypose.model_dump(),
            exitpose_local_json=payload.exitpose.model_dump(),
            marker_id=payload.marker_id,
            charger_type=payload.charger_type,
            meta_data={
                "precision_required": payload.precision_required,
                "marker_family": payload.marker_family,
                "marker_size_m": payload.marker_size_m,
                "markerpose_covariance": list(payload.markerpose_covariance or []),
                "marker_visible": False,
                "last_observed_at": None,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return dock_out(row)


@router.put("/maps/{warehouse_map_id}/docks/{dock_id}", response_model=WarehouseDockOut)
async def update_warehouse_dock(
    warehouse_map_id: int,
    dock_id: int,
    payload: WarehouseDockUpdateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseDockOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    fields_set = getattr(payload, "model_fields_set", set())
    values: dict[str, Any] = {}
    if "name" in fields_set and payload.name is not None:
        values["name"] = payload.name.strip()
    for field_name, column_name in (
        ("pose", "pose_local_json"),
        ("entrypose", "entrypose_local_json"),
        ("exitpose", "exitpose_local_json"),
    ):
        pose = getattr(payload, field_name)
        if field_name in fields_set and pose is not None:
            values[column_name] = pose.model_dump()
    for field_name in ("marker_id", "charger_type"):
        if field_name in fields_set:
            values[field_name] = getattr(payload, field_name)
    meta_values = {
        key: value
        for key, value in {
            "precision_required": payload.precision_required,
            "marker_family": payload.marker_family,
            "marker_size_m": payload.marker_size_m,
            "markerpose_covariance": payload.markerpose_covariance,
        }.items()
        if key in fields_set
    }
    if meta_values:
        current = next(
            (
                dock
                for dock in await repo.list_dock_stations(
                    db, warehouse_map_id=warehouse_map_id
                )
                if int(dock.id) == dock_id
            ),
            None,
        )
        meta_data = dict(current.meta_data or {}) if current is not None else {}
        meta_data.update(meta_values)
        values["meta_data"] = meta_data
    row = await repo.update_dock_station(
        db, dock_id=dock_id, warehouse_map_id=warehouse_map_id, values=values
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Warehouse dock not found")
    await db.commit()
    return dock_out(row)


@router.delete("/maps/{warehouse_map_id}/docks/{dock_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse_dock(
    warehouse_map_id: int,
    dock_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    deleted = await repo.deactivate_dock_station(
        db, warehouse_map_id=warehouse_map_id, dock_id=dock_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse dock not found")
    await db.commit()


