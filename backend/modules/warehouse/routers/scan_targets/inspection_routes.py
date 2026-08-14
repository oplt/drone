"""Warehouse scan-target routes — inspection missions."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_mission_exec, require_org_user
from backend.modules.warehouse.http_helpers import inspection_mission_out, inspection_result_out
from backend.modules.warehouse.models import (
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseScanTarget,
)
from backend.modules.warehouse.schemas import (
    WarehouseInspectionMissionCreate,
    WarehouseInspectionMissionRead,
    WarehouseInspectionResultRead,
)

from backend.modules.warehouse.routers import scan_targets as scan_targets_api

from .router import router
from .schemas import InspectionMissionApprovalIn

logger = logging.getLogger(__name__)


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
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    coordinate_frame = await scan_targets_api.get_locked_coordinate_frame(db, warehouse_map_id)
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
    pins = await scan_targets_api.create_mission_revision_pins(
        db,
        warehouse_map_id=warehouse_map_id,
        coordinate_frame_id=int(coordinate_frame.id),
        targets=[by_id[int(target_id)] for target_id in payload.target_ids],
        return_to_dock=bool(payload.return_to_dock),
        battery_pct=float(payload.available_battery_pct),
    )
    ordered_targets = scan_targets_api.order_targets(
        [by_id[int(target_id)] for target_id in payload.target_ids],
        optimize_order=payload.optimize_order,
    )
    waypoints = scan_targets_api.build_inspection_waypoints(
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
    scan_targets_api.emit_coordinate_audit(
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
        transform_age_ms_value=scan_targets_api.transform_age_ms(getattr(coordinate_frame, "locked_at", None)),
        validation_result="pass",
        extra={
            "validation_result_id": pins.validation_result_id,
            "layout_version_id": pins.layout_version_id,
            "map_model_id": pins.map_model_id,
            "target_count": len(ordered_targets),
            "artifact_checksums": pins.artifact_checksums,
        },
    )
    scan_targets_api.metric_add("warehouse_inspection_missions_planned_total", 1)
    return inspection_mission_out(row)


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
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
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
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=int(row.warehouse_map_id), user=org_user.user)
    return inspection_mission_out(row)


@router.get(
    "/inspection-missions/{mission_id}/results",
    response_model=Page[WarehouseInspectionResultRead],
)
async def list_warehouse_inspection_results(
    mission_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> Page[WarehouseInspectionResultRead]:
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    mission = (
        await db.execute(
            select(WarehouseInspectionMission).where(WarehouseInspectionMission.id == mission_id)
        )
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="Warehouse inspection mission not found")
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
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
                .limit(page_limit + 1)
                .offset(page_offset)
            )
        )
        .scalars()
        .all()
    )
    return page_from_offset(
        [inspection_result_out(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
        total=total,
    )
