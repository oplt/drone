from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import (
    OrgUser,
    require_mission_exec,
    require_org_user,
    require_org_write,
)
from backend.modules.warehouse.http_access import (
    get_map_or_404,
)
from backend.modules.warehouse.http_helpers import (
    get_scan_target_or_404,
    inspection_mission_out,
    inspection_result_out,
    scan_target_out,
)
from backend.modules.warehouse.http_models import *
from backend.modules.warehouse.models import (
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseScanTarget,
)
from backend.modules.warehouse.schemas import (
    WarehouseInspectionMissionCreate,
    WarehouseInspectionMissionRead,
    WarehouseInspectionResultPage,
    WarehouseInspectionResultRead,
    WarehouseScanPoseComputeIn,
    WarehouseScanPoseComputeOut,
    WarehouseScanTargetCreate,
    WarehouseScanTargetImport,
    WarehouseScanTargetPage,
    WarehouseScanTargetRead,
    WarehouseScanTargetUpdate,
)
from backend.modules.warehouse.service.coordinate_audit import (
    emit_coordinate_audit,
    transform_age_ms,
)
from backend.modules.warehouse.service.coordinate_frames import (
    get_locked_coordinate_frame,
    require_warehouse_map_frames,
)
from backend.modules.warehouse.service.frame_imports import normalize_scan_target_import
from backend.modules.warehouse.service.inspection import (
    MockWarehouseScanner,
    build_inspection_waypoints,
    compute_scan_pose,
    order_targets,
)
from backend.modules.warehouse.service.inspection_feedback import (
    append_rescan_plan,
    persist_inspection_feedback,
    persist_layout_drift_report,
)
from backend.modules.warehouse.service.layout import resolve_bin_context
from backend.modules.warehouse.service.mission_revisions import (
    create_mission_revision_pins,
    is_legacy_mission,
    require_legacy_same_origin_confirmation,
    verify_mission_revision_pins,
)
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    record_mission_rejection,
)
from backend.modules.warehouse.service.provisional_mapping import block_executable_mission
from backend.modules.warehouse.service.slam_localization_monitor import (
    validate_slam_localization_for_execution,
)
from backend.observability.metrics import add as metric_add

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
            await db.execute(select(func.count()).select_from(WarehouseScanTarget).where(*clauses))
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
    frame = await get_locked_coordinate_frame(db, warehouse_map_id)
    if payload.coordinate_frame_id is not None and payload.coordinate_frame_id != int(frame.id):
        raise HTTPException(
            status_code=409,
            detail="Displayed coordinate revision is stale; reload the warehouse map",
        )
    require_warehouse_map_frames(
        [payload.target_point_local_json.model_dump(), payload.scan_pose_local_json.model_dump()]
    )
    location = await resolve_bin_context(
        db,
        warehouse_map_id=warehouse_map_id,
        bin_id=payload.bin_id,
        aisle_code=payload.aisle_code,
        rack_code=payload.rack_code,
        shelf_level=payload.shelf_level,
        bin_code=payload.bin_code,
    )
    if location.coordinate_frame_id != int(frame.id):
        raise HTTPException(409, "Locked layout uses a different coordinate revision")
    row = WarehouseScanTarget(
        warehouse_map_id=warehouse_map_id,
        reference_model_id=payload.reference_model_id,
        dock_station_id=payload.dock_station_id,
        layout_version_id=location.layout_version_id,
        bin_id=location.bin_id,
        aisle_code=location.aisle_code,
        rack_code=location.rack_code,
        shelf_level=location.shelf_level,
        bin_code=location.bin_code,
        sku=payload.sku,
        barcode=payload.barcode,
        product_name=payload.product_name,
        target_point_local_json=payload.target_point_local_json.model_dump(),
        coordinate_frame_id=int(frame.id),
        scan_pose_local_json=payload.scan_pose_local_json.model_dump(),
        sensor_aim_json=(
            payload.sensor_aim_json.model_dump() if payload.sensor_aim_json is not None else None
        ),
        shelf_normal_local_json=(
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        ),
        scanner_metadata_json=dict(payload.scanner_metadata_json or {}),
        path_validation_json=dict(payload.path_validation_json or {}),
        failure_reason=payload.failure_reason,
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
    frame = await get_locked_coordinate_frame(db, warehouse_map_id)
    if payload.coordinate_frame_id is not None and payload.coordinate_frame_id != int(frame.id):
        raise HTTPException(409, "Import coordinate revision is stale")
    rows: list[WarehouseScanTarget] = []
    try:
        for raw_target in payload.targets:
            try:
                target = normalize_scan_target_import(
                    raw_target,
                    source_frame_id=payload.source_frame_id,
                    odom_to_warehouse_map_transform=frame.transform_json,
                )
            except ValueError as exc:
                raise HTTPException(422, f"Invalid scan target import: {exc}") from exc
            if target.coordinate_frame_id is not None and target.coordinate_frame_id != int(
                frame.id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Imported target coordinate revision is stale",
                )
            location = await resolve_bin_context(
                db,
                warehouse_map_id=warehouse_map_id,
                bin_id=target.bin_id,
                aisle_code=target.aisle_code,
                rack_code=target.rack_code,
                shelf_level=target.shelf_level,
                bin_code=target.bin_code,
            )
            if location.coordinate_frame_id != int(frame.id):
                raise HTTPException(409, "Locked layout uses a different coordinate revision")
            row = WarehouseScanTarget(
                warehouse_map_id=warehouse_map_id,
                coordinate_frame_id=int(frame.id),
                layout_version_id=location.layout_version_id,
                bin_id=location.bin_id,
                reference_model_id=target.reference_model_id,
                dock_station_id=target.dock_station_id,
                aisle_code=location.aisle_code,
                rack_code=location.rack_code,
                shelf_level=location.shelf_level,
                bin_code=location.bin_code,
                sku=target.sku,
                barcode=target.barcode,
                product_name=target.product_name,
                target_point_local_json=target.target_point_local_json.model_dump(),
                scan_pose_local_json=target.scan_pose_local_json.model_dump(),
                sensor_aim_json=(
                    target.sensor_aim_json.model_dump()
                    if target.sensor_aim_json is not None
                    else None
                ),
                shelf_normal_local_json=(
                    target.shelf_normal_local_json.model_dump()
                    if target.shelf_normal_local_json is not None
                    else None
                ),
                scanner_metadata_json=dict(target.scanner_metadata_json or {}),
                path_validation_json=dict(target.path_validation_json or {}),
                failure_reason=target.failure_reason,
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
    emit_coordinate_audit(
        event_name="warehouse_scan_targets_imported",
        action="transform_import" if payload.source_frame_id == "odom" else "import_layout",
        resource_type="warehouse_scan_target_batch",
        resource_id=f"map:{warehouse_map_id}:frame:{frame.id}",
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason=f"operator_import_from_{payload.source_frame_id}",
        coordinate_frame_id=int(frame.id),
        coordinate_frame_version=int(frame.version),
        covariance=list(getattr(frame, "covariance_json", None) or []),
        transform_age_ms_value=transform_age_ms(getattr(frame, "locked_at", None)),
        validation_result="pass",
        extra={
            "source_frame_id": payload.source_frame_id,
            "target_frame_id": "warehouse_map",
            "target_count": len(rows),
            "transform_applied": payload.source_frame_id == "odom",
        },
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
    location_fields = {"bin_id", "aisle_code", "rack_code", "shelf_level", "bin_code"}
    if fields_set & location_fields:
        location = await resolve_bin_context(
            db,
            warehouse_map_id=warehouse_map_id,
            bin_id=payload.bin_id if "bin_id" in fields_set else row.bin_id,
            aisle_code=(
                payload.aisle_code
                if "aisle_code" in fields_set and payload.aisle_code is not None
                else row.aisle_code
            ),
            rack_code=payload.rack_code if "rack_code" in fields_set else row.rack_code,
            shelf_level=(payload.shelf_level if "shelf_level" in fields_set else row.shelf_level),
            bin_code=payload.bin_code if "bin_code" in fields_set else row.bin_code,
        )
        row.layout_version_id = location.layout_version_id
        row.bin_id = location.bin_id
        row.aisle_code = location.aisle_code
        row.rack_code = location.rack_code
        row.shelf_level = location.shelf_level
        row.bin_code = location.bin_code
    for field_name in (
        "reference_model_id",
        "dock_station_id",
        "sku",
        "barcode",
        "product_name",
        "standoff_m",
        "hover_time_s",
        "scan_timeout_s",
        "priority",
        "active",
        "failure_reason",
    ):
        if field_name in fields_set:
            setattr(row, field_name, getattr(payload, field_name))
    if "target_point_local_json" in fields_set and payload.target_point_local_json is not None:
        row.target_point_local_json = payload.target_point_local_json.model_dump()
    if "scan_pose_local_json" in fields_set and payload.scan_pose_local_json is not None:
        row.scan_pose_local_json = payload.scan_pose_local_json.model_dump()
    if "sensor_aim_json" in fields_set:
        row.sensor_aim_json = (
            payload.sensor_aim_json.model_dump() if payload.sensor_aim_json is not None else None
        )
    if "shelf_normal_local_json" in fields_set:
        row.shelf_normal_local_json = (
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        )
    if "scanner_metadata_json" in fields_set:
        row.scanner_metadata_json = dict(payload.scanner_metadata_json or {})
    if "path_validation_json" in fields_set:
        row.path_validation_json = dict(payload.path_validation_json or {})
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
            "scan_pose_local_json": row.scan_pose_local_json,
            "sensor_aim_json": row.sensor_aim_json,
            "shelf_normal_local_json": row.shelf_normal_local_json,
            "scanner_metadata_json": row.scanner_metadata_json,
            "path_validation_json": row.path_validation_json,
            "failure_reason": row.failure_reason,
            "standoff_m": row.standoff_m,
            "hover_time_s": row.hover_time_s,
            "scan_timeout_s": row.scan_timeout_s,
            "priority": row.priority,
            "active": row.active,
        }
    )
    row.target_point_local_json = validated.target_point_local_json.model_dump()
    row.scan_pose_local_json = validated.scan_pose_local_json.model_dump()
    row.sensor_aim_json = (
        validated.sensor_aim_json.model_dump() if validated.sensor_aim_json is not None else None
    )
    row.shelf_normal_local_json = (
        validated.shelf_normal_local_json.model_dump()
        if validated.shelf_normal_local_json is not None
        else None
    )
    row.scanner_metadata_json = dict(validated.scanner_metadata_json or {})
    row.path_validation_json = dict(validated.path_validation_json or {})
    row.failure_reason = validated.failure_reason
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
async def compute_warehouse_scan_pose(
    payload: WarehouseScanPoseComputeIn,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanPoseComputeOut:
    return WarehouseScanPoseComputeOut(
        scan_pose=compute_scan_pose(
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
    coordinate_frame = await get_locked_coordinate_frame(db, warehouse_map_id)
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
    wrong_revision = [
        int(row.id) for row in rows if row.coordinate_frame_id != int(coordinate_frame.id)
    ]
    if wrong_revision:
        raise HTTPException(
            status_code=409,
            detail=(
                "Scan targets do not use locked coordinate revision "
                f"{coordinate_frame.version}: {wrong_revision}"
            ),
        )
    pins = await create_mission_revision_pins(
        db,
        warehouse_map_id=warehouse_map_id,
        coordinate_frame_id=int(coordinate_frame.id),
        targets=[by_id[int(target_id)] for target_id in payload.target_ids],
        return_to_dock=bool(payload.return_to_dock),
        battery_pct=float(payload.available_battery_pct),
    )
    ordered_targets = order_targets(
        [by_id[int(target_id)] for target_id in payload.target_ids],
        optimize_order=payload.optimize_order,
    )
    waypoints = build_inspection_waypoints(
        ordered_targets,
        default_hover_time_s=payload.default_hover_time_s,
        default_scan_timeout_s=payload.default_scan_timeout_s,
    )
    plan = {
        "frame_id": "warehouse_map",
        "coordinate_frame_id": int(coordinate_frame.id),
        "coordinate_frame_version": int(coordinate_frame.version),
        "layout_version_id": pins.layout_version_id,
        "layout_version": pins.layout_version,
        "map_model_id": pins.map_model_id,
        "map_model_version": pins.map_model_version,
        "validation_result_id": pins.validation_result_id,
        "artifact_checksums": pins.artifact_checksums,
        "warehouse_map_to_odom_transform": coordinate_frame.transform_json,
        "preflight_relocalization": {
            "required": True,
            "status": "pending",
            "reason": "inspection_mission_start",
        },
        "waypoints": [waypoint.model_dump() for waypoint in waypoints],
        "rescan_waypoints": [],
        "warnings": [],
    }
    plan_checksum = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    row = WarehouseInspectionMission(
        warehouse_map_id=warehouse_map_id,
        coordinate_frame_id=int(coordinate_frame.id),
        layout_version_id=pins.layout_version_id,
        map_model_id=pins.map_model_id,
        validation_result_id=pins.validation_result_id,
        artifact_checksums_json=pins.artifact_checksums,
        name=payload.name.strip(),
        status="planned",
        scan_mode=payload.scan_mode,
        return_to_dock=bool(payload.return_to_dock),
        target_ids_json=[int(target.id) for target in ordered_targets],
        plan_json=plan,
        plan_checksum=plan_checksum,
        approval_status="pending",
        runtime_policy_json={
            "max_replans_per_leg": 2,
            "abort_on_version_change": True,
            "abort_on_tf_loss": True,
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
    emit_coordinate_audit(
        event_name="warehouse_mission_transform_pinned",
        action="pin_mission_transform",
        resource_type="warehouse_inspection_mission",
        resource_id=row.id,
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason="mission_plan_validated_against_locked_revisions",
        coordinate_frame_id=int(coordinate_frame.id),
        coordinate_frame_version=int(coordinate_frame.version),
        new_value=coordinate_frame.transform_json,
        covariance=list(getattr(coordinate_frame, "covariance_json", None) or []),
        transform_age_ms_value=transform_age_ms(getattr(coordinate_frame, "locked_at", None)),
        validation_result="pass",
        extra={
            "validation_result_id": pins.validation_result_id,
            "layout_version_id": pins.layout_version_id,
            "map_model_id": pins.map_model_id,
            "target_count": len(ordered_targets),
            "artifact_checksums": pins.artifact_checksums,
        },
    )
    metric_add("warehouse_inspection_missions_planned_total", 1)
    return inspection_mission_out(row)


class InspectionMissionApprovalIn(BaseModel):
    approved: bool


@router.post(
    "/inspection-missions/{mission_id}/approval",
    response_model=WarehouseInspectionMissionRead,
)
async def approve_warehouse_inspection_mission(
    mission_id: int,
    payload: InspectionMissionApprovalIn,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseInspectionMissionRead:
    mission = await db.get(WarehouseInspectionMission, mission_id)
    if mission is None:
        raise HTTPException(404, "Warehouse inspection mission not found")
    await get_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
    expected = str(if_match or "").strip().removeprefix("W/").strip('"')
    if not expected or expected != str(mission.plan_checksum or ""):
        raise HTTPException(412, "Mission preview checksum mismatch")
    if mission.status != "planned":
        raise HTTPException(409, "Only planned missions can be approved")
    mission.approval_status = "approved" if payload.approved else "rejected"
    mission.approved_at = datetime.now(UTC) if payload.approved else None
    mission.approved_by_id = getattr(org_user.user, "id", None) if payload.approved else None
    await db.commit()
    await db.refresh(mission)
    return inspection_mission_out(mission)


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
    same_origin_confirmed: bool = Header(False, alias="X-Confirm-Same-Origin"),
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
    if mission.approval_status != "approved":
        raise HTTPException(409, "Mission preview must be approved before execution")
    checksum = hashlib.sha256(
        json.dumps(
            mission.plan_json or {}, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    if not mission.plan_checksum or checksum != mission.plan_checksum:
        raise HTTPException(409, "Mission plan changed after approval")
    legacy = is_legacy_mission(mission)
    require_legacy_same_origin_confirmation(
        mission, same_origin_confirmed=same_origin_confirmed is True
    )
    coordinate_frame = await get_locked_coordinate_frame(db, int(mission.warehouse_map_id))
    if block_executable_mission(
        coordinate_frame_status=str(getattr(coordinate_frame, "status", "locked")),
        localization_method=str(getattr(coordinate_frame, "localization_method", "") or ""),
    ):
        record_mission_rejection(reason="provisional_coordinates")
        raise HTTPException(
            status_code=409,
            detail="Executable missions are blocked while coordinates are provisional",
        )
    try:
        localization_method = str(getattr(coordinate_frame, "localization_method", "") or "")
        if localization_method.lower() in {
            "live_slam",
            "provisional_slam",
            "scan_provisional",
            "vslam",
        }:
            validate_slam_localization_for_execution()
    except ValueError as exc:
        record_mission_rejection(reason="slam_localization_stale")
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    if not legacy and mission.coordinate_frame_id != int(coordinate_frame.id):
        raise HTTPException(
            status_code=409,
            detail="Mission coordinate revision is stale; create a new mission after localization",
        )
    if legacy:
        logger.warning(
            "legacy_warehouse_mission_same_origin_override mission_id=%s map_id=%s",
            mission.id,
            mission.warehouse_map_id,
        )
        metric_add("warehouse_legacy_mission_same_origin_overrides_total", 1)
    else:
        await verify_mission_revision_pins(db, mission)
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
        plan = dict(mission.plan_json or {})
        plan["preflight_relocalization"] = {
            "required": True,
            "status": "passed",
            "reason": "mock_execution_localization_check",
            "checked_at": datetime.now(UTC).isoformat(),
        }
        mission.plan_json = plan
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
                drone_pose_local_json=target.scan_pose_local_json,
                error_message=scan.error_message,
            )
            db.add(result)
            await db.flush()
            try:
                await persist_inspection_feedback(
                    db,
                    mission=mission,
                    target=target,
                    result=result,
                )
                append_rescan_plan(mission, target=target, result=result)
            except Exception:
                logger.exception(
                    "warehouse_inspection_mock_feedback_failed",
                    extra={"mission_id": int(mission.id), "target_id": int(target.id)},
                )
            results.append(result)
        mission.status = "completed"
        try:
            await persist_layout_drift_report(db, mission=mission)
        except Exception:
            logger.exception(
                "warehouse_inspection_mock_drift_report_failed",
                extra={"mission_id": int(mission.id)},
            )
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
