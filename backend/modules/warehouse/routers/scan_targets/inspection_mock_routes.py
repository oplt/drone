"""Warehouse scan-target routes — mock inspection execution."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_mission_exec
from backend.modules.warehouse.http_helpers import inspection_result_out
from backend.modules.warehouse.models import (
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseScanTarget,
)
from backend.modules.warehouse.schemas import WarehouseInspectionResultRead
from backend.modules.warehouse.routers import scan_targets as scan_targets_api

from .router import router

logger = logging.getLogger(__name__)


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
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=int(mission.warehouse_map_id), user=org_user.user)
    if mission.approval_status != "approved":
        raise HTTPException(409, "Mission preview must be approved before execution")
    checksum = hashlib.sha256(
        json.dumps(
            mission.plan_json or {}, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    if not mission.plan_checksum or checksum != mission.plan_checksum:
        raise HTTPException(409, "Mission plan changed after approval")
    legacy = scan_targets_api.is_legacy_mission(mission)
    scan_targets_api.require_legacy_same_origin_confirmation(
        mission, same_origin_confirmed=same_origin_confirmed is True
    )
    coordinate_frame = await scan_targets_api.get_locked_coordinate_frame(db, int(mission.warehouse_map_id))
    if scan_targets_api.block_executable_mission(
        coordinate_frame_status=str(getattr(coordinate_frame, "status", "locked")),
        localization_method=str(getattr(coordinate_frame, "localization_method", "") or ""),
    ):
        scan_targets_api.record_mission_rejection(reason="provisional_coordinates")
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
            scan_targets_api.validate_slam_localization_for_execution()
    except ValueError as exc:
        scan_targets_api.record_mission_rejection(reason="slam_localization_stale")
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
        scan_targets_api.metric_add("warehouse_legacy_mission_same_origin_overrides_total", 1)
    else:
        await scan_targets_api.verify_mission_revision_pins(db, mission)
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
    scanner = scan_targets_api.MockWarehouseScanner()
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
                await scan_targets_api.persist_inspection_feedback(
                    db,
                    mission=mission,
                    target=target,
                    result=result,
                )
                scan_targets_api.append_rescan_plan(mission, target=target, result=result)
            except Exception:
                logger.exception(
                    "warehouse_inspection_mock_feedback_failed",
                    extra={"mission_id": int(mission.id), "target_id": int(target.id)},
                )
            results.append(result)
        mission.status = "completed"
        try:
            await scan_targets_api.persist_layout_drift_report(db, mission=mission)
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
