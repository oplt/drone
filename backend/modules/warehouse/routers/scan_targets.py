from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, File, HTTPException, Query, Response, UploadFile, status
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
    WarehouseInspectionResultPage,
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


def _set_scan_target_cache_headers(response: Response, *, offset: int) -> None:
    response.headers["Cache-Control"] = (
        "private, max-age=10" if offset == 0 else "private, no-store"
    )
    response.headers["Vary"] = "Authorization"

@router.get("/maps/{warehouse_map_id}/scan-targets", response_model=WarehouseScanTargetPage)
async def list_warehouse_scan_targets(
    warehouse_map_id: int,
    response: Response,
    active: bool | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanTargetPage:
    _set_scan_target_cache_headers(response, offset=offset)
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    clauses = [WarehouseScanTarget.warehouse_map_id == warehouse_map_id]
    if active is not None:
        clauses.append(WarehouseScanTarget.active.is_(active))
    total = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WarehouseScanTarget)
                .where(*clauses)
            )
        ).scalar_one()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(WarehouseScanTarget)
                .where(*clauses)
                .order_by(
                    WarehouseScanTarget.priority.asc(),
                    WarehouseScanTarget.aisle_code.asc(),
                    WarehouseScanTarget.rack_code.asc(),
                    WarehouseScanTarget.bin_code.asc(),
                    WarehouseScanTarget.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return WarehouseScanTargetPage(
        items=[scan_target_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/maps/{warehouse_map_id}/scan-targets",
    response_model=WarehouseScanTargetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_scan_target(
    warehouse_map_id: int,
    payload: WarehouseScanTargetCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseScanTargetRead:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = WarehouseScanTarget(
        warehouse_map_id=warehouse_map_id,
        reference_model_id=payload.reference_model_id,
        dock_station_id=payload.dock_station_id,
        aisle_code=payload.aisle_code.strip(),
        rack_code=payload.rack_code,
        shelf_level=payload.shelf_level,
        bin_code=payload.bin_code,
        sku=payload.sku,
        barcode=payload.barcode,
        product_name=payload.product_name,
        target_point_local_json=payload.target_point_local_json.model_dump(),
        scanpose_local_json=payload.scanpose_local_json.model_dump(),
        shelf_normal_local_json=(
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        ),
        standoff_m=float(payload.standoff_m),
        hover_time_s=float(payload.hover_time_s),
        scan_timeout_s=float(payload.scan_timeout_s),
        priority=int(payload.priority),
        active=bool(payload.active),
    )
    try:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_scan_target_created",
        extra={"warehouse_map_id": warehouse_map_id, "target_id": int(row.id)},
    )
    return scan_target_out(row)


@router.post(
    "/maps/{warehouse_map_id}/scan-targets/import",
    response_model=list[WarehouseScanTargetRead],
    status_code=status.HTTP_201_CREATED,
)
async def import_warehouse_scan_targets(
    warehouse_map_id: int,
    payload: WarehouseScanTargetImport,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> list[WarehouseScanTargetRead]:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows: list[WarehouseScanTarget] = []
    try:
        for target in payload.targets:
            row = WarehouseScanTarget(
                warehouse_map_id=warehouse_map_id,
                reference_model_id=target.reference_model_id,
                dock_station_id=target.dock_station_id,
                aisle_code=target.aisle_code.strip(),
                rack_code=target.rack_code,
                shelf_level=target.shelf_level,
                bin_code=target.bin_code,
                sku=target.sku,
                barcode=target.barcode,
                product_name=target.product_name,
                target_point_local_json=target.target_point_local_json.model_dump(),
                scan_pose_local_json=target.scan_pose_local_json.model_dump(),
                shelf_normal_local_json=(
                    target.shelf_normal_local_json.model_dump()
                    if target.shelf_normal_local_json is not None
                    else None
                ),
                standoff_m=float(target.standoff_m),
                hover_time_s=float(target.hover_time_s),
                scan_timeout_s=float(target.scan_timeout_s),
                priority=int(target.priority),
                active=bool(target.active),
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        row_ids = [int(row.id) for row in rows]
        persisted_rows = list(
            (
                await db.execute(
                    select(WarehouseScanTarget)
                    .where(WarehouseScanTarget.id.in_(row_ids))
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        persisted_by_id = {int(row.id): row for row in persisted_rows}
        if len(persisted_by_id) != len(row_ids):
            raise RuntimeError("Failed to reload all imported warehouse scan targets")
        rows = [persisted_by_id[row_id] for row_id in row_ids]
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_scan_targets_imported",
        extra={"warehouse_map_id": warehouse_map_id, "count": len(rows)},
    )
    return [scan_target_out(row) for row in rows]


@router.get(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    response_model=WarehouseScanTargetRead,
)
async def get_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanTargetRead:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    return scan_target_out(row)


@router.patch(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    response_model=WarehouseScanTargetRead,
)
async def update_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    payload: WarehouseScanTargetUpdate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseScanTargetRead:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    fields_set = getattr(payload, "model_fields_set", set())
    for field_name in (
        "reference_model_id",
        "dock_station_id",
        "rack_code",
        "shelf_level",
        "bin_code",
        "sku",
        "barcode",
        "product_name",
        "standoff_m",
        "hover_time_s",
        "scan_timeout_s",
        "priority",
        "active",
    ):
        if field_name in fields_set:
            setattr(row, field_name, getattr(payload, field_name))
    if "aisle_code" in fields_set and payload.aisle_code is not None:
        row.aisle_code = payload.aisle_code.strip()
    if "target_point_local_json" in fields_set and payload.target_point_local_json is not None:
        row.target_point_local_json = payload.target_point_local_json.model_dump()
    if "scanpose_local_json" in fields_set and payload.scanpose_local_json is not None:
        row.scanpose_local_json = payload.scanpose_local_json.model_dump()
    if "shelf_normal_local_json" in fields_set:
        row.shelf_normal_local_json = (
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        )
    validated = WarehouseScanTargetCreate.model_validate(
        {
            "reference_model_id": row.reference_model_id,
            "dock_station_id": row.dock_station_id,
            "aisle_code": row.aisle_code,
            "rack_code": row.rack_code,
            "shelf_level": row.shelf_level,
            "bin_code": row.bin_code,
            "sku": row.sku,
            "barcode": row.barcode,
            "product_name": row.product_name,
            "target_point_local_json": row.target_point_local_json,
            "scanpose_local_json": row.scanpose_local_json,
            "shelf_normal_local_json": row.shelf_normal_local_json,
            "standoff_m": row.standoff_m,
            "hover_time_s": row.hover_time_s,
            "scan_timeout_s": row.scan_timeout_s,
            "priority": row.priority,
            "active": row.active,
        }
    )
    row.target_point_local_json = validated.target_point_local_json.model_dump()
    row.scanpose_local_json = validated.scanpose_local_json.model_dump()
    row.shelf_normal_local_json = (
        validated.shelf_normal_local_json.model_dump()
        if validated.shelf_normal_local_json is not None
        else None
    )
    try:
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    return scan_target_out(row)


@router.delete(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    row.active = False
    await db.commit()


@router.post("/scan-targets/compute-scan-pose", response_model=WarehouseScanPoseComputeOut)
async def compute_warehouse_scanpose(
    payload: WarehouseScanPoseComputeIn,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanPoseComputeOut:
    return WarehouseScanPoseComputeOut(
        scanpose=compute_scanpose(
            target_point=payload.target_point,
            shelf_normal=payload.shelf_normal,
            standoff_m=payload.standoff_m,
            yaw_deg=payload.yaw_deg,
        )
    )


@router.post(
    "/inspection-missions",
    response_model=WarehouseInspectionMissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_inspection_mission(
    payload: WarehouseInspectionMissionCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseInspectionMissionRead:
    warehouse_map_id = int(payload.warehouse_map_id)
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = (
        (
            await db.execute(
                select(WarehouseScanTarget).where(
                    WarehouseScanTarget.id.in_(payload.target_ids),
                    WarehouseScanTarget.warehouse_map_id == warehouse_map_id,
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {int(row.id): row for row in rows}
    missing = [target_id for target_id in payload.target_ids if int(target_id) not in by_id]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Scan targets not found for selected map: {missing}",
        )
    inactive = [int(row.id) for row in rows if not row.active]
    if inactive:
        raise HTTPException(status_code=400, detail=f"Scan targets are inactive: {inactive}")
    ordered_targets = order_targets(
        [by_id[int(target_id)] for target_id in payload.target_ids],
        optimize_order=payload.optimize_order,
    )
    waypoints = build_inspection_waypoints(
        ordered_targets,
        default_hover_time_s=payload.default_hover_time_s,
        default_scan_timeout_s=payload.default_scan_timeout_s,
    )
    row = WarehouseInspectionMission(
        warehouse_map_id=warehouse_map_id,
        name=payload.name.strip(),
        status="planned",
        scan_mode=payload.scan_mode,
        return_to_dock=bool(payload.return_to_dock),
        target_ids_json=[int(target.id) for target in ordered_targets],
        plan_json={
            "frame_id": "warehouse_map",
            "warehouse_map_to_odom_transform": None,
            "waypoints": [waypoint.model_dump() for waypoint in waypoints],
            "warnings": [
                "ESDF clearance validation not wired in MVP.",
                "warehouse_map == odom assumed until persistent localization is added.",
            ],
        },
    )
    try:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_inspection_mission_planned",
        extra={"mission_id": int(row.id), "target_count": len(ordered_targets)},
    )
    metric_add("warehouse_inspection_missions_planned_total", 1)
    return inspection_mission_out(row)


@router.get(
    "/inspection-missions/{mission_id}",
    response_model=WarehouseInspectionMissionRead,
)
async def get_warehouse_inspection_mission(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseInspectionMissionRead:
    row = (
        await db.execute(
            select(WarehouseInspectionMission).where(WarehouseInspectionMission.id == mission_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Warehouse inspection mission not found")
    await get_map_or_404(db, warehouse_map_id=int(row.warehouse_map_id), user=org_user.user)
    return inspection_mission_out(row)


@router.post(
    "/inspection-missions/{mission_id}/run-mock",
    response_model=list[WarehouseInspectionResultRead],
)
async def run_warehouse_inspection_mission_mock(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> list[WarehouseInspectionResultRead]:
    mission = (
        await db.execute(
            select(WarehouseInspectionMission).where(WarehouseInspectionMission.id == mission_id)
        )
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="Warehouse inspection mission not found")
    await get_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
    target_ids = [int(value) for value in (mission.target_ids_json or [])]
    targets = (
        (
            await db.execute(
                select(WarehouseScanTarget).where(WarehouseScanTarget.id.in_(target_ids))
            )
        )
        .scalars()
        .all()
    )
    by_id = {int(target.id): target for target in targets}
    ordered = [by_id[target_id] for target_id in target_ids if target_id in by_id]
    scanner = MockWarehouseScanner()
    mission.status = "running"
    results: list[WarehouseInspectionResult] = []
    try:
        for target in ordered:
            logger.info(
                "warehouse_inspection_scan_started",
                extra={"mission_id": int(mission.id), "target_id": int(target.id)},
            )
            scan = await scanner.scan_target(target, timeout_s=float(target.scan_timeout_s))
            result = WarehouseInspectionResult(
                mission_id=int(mission.id),
                target_id=int(target.id),
                status=scan.status,
                expected_barcode=target.barcode,
                detected_barcode=scan.detected_barcode,
                confidence=scan.confidence,
                image_asset_id=scan.image_asset_id,
                video_asset_id=scan.video_asset_id,
                dronepose_local_json=target.scanpose_local_json,
                error_message=scan.error_message,
            )
            db.add(result)
            results.append(result)
        mission.status = "completed"
        await db.commit()
        for result in results:
            await db.refresh(result)
    except Exception:
        mission.status = "failed"
        await db.rollback()
        raise
    logger.info(
        "warehouse_inspection_mission_completed",
        extra={"mission_id": int(mission.id), "status": mission.status},
    )
    return [inspection_result_out(row) for row in results]


@router.get(
    "/inspection-missions/{mission_id}/results",
    response_model=WarehouseInspectionResultPage,
)
async def list_warehouse_inspection_results(
    mission_id: int,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseInspectionResultPage:
    mission = (
        await db.execute(
            select(WarehouseInspectionMission).where(WarehouseInspectionMission.id == mission_id)
        )
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="Warehouse inspection mission not found")
    await get_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
    total = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WarehouseInspectionResult)
                .where(WarehouseInspectionResult.mission_id == mission_id)
            )
        ).scalar_one()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(WarehouseInspectionResult)
                .where(WarehouseInspectionResult.mission_id == mission_id)
                .order_by(
                    WarehouseInspectionResult.scanned_at.asc(),
                    WarehouseInspectionResult.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return WarehouseInspectionResultPage(
        items=[inspection_result_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
