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
from backend.core.config.runtime import settings
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
    WarehouseStructureDryRunOut,
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
    WarehouseRackTemplate,
    WarehouseRackTemplateVersion,
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
    create_durable_extraction_job,
    dry_run_structure_extraction,
    ensure_structure_quality_summary,
    get_extraction_state,
    get_durable_extraction_state,
    record_extraction_queued,
    update_durable_extraction_job,
    resolve_latest_model_flight,
    warehouse_mapping_worker_ready,
)
from backend.modules.warehouse.service.rack_templates import template_params_payload
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


async def _resolve_template_payload(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    params_payload: dict[str, Any],
) -> dict[str, Any]:
    version_id = params_payload.get("rack_template_version_id")
    if version_id is None:
        return params_payload
    row = (
        await db.execute(
            select(WarehouseRackTemplate, WarehouseRackTemplateVersion)
            .join(
                WarehouseRackTemplateVersion,
                WarehouseRackTemplateVersion.template_id == WarehouseRackTemplate.id,
            )
            .where(
                WarehouseRackTemplate.warehouse_map_id == int(warehouse_map_id),
                WarehouseRackTemplateVersion.id == int(version_id),
                WarehouseRackTemplate.active.is_(True),
                WarehouseRackTemplateVersion.status.in_(("active", "draft")),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Rack template version not found")
    _template, version = row
    resolved = dict(params_payload)
    for key, value in template_params_payload(version).items():
        if value is not None:
            resolved[key] = value
    return resolved

@router.post(
    "/maps/{warehouse_map_id}/structure/extract",
    response_model=WarehouseStructureExtractOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_warehouse_structure_endpoint(
    warehouse_map_id: int,
    payload: WarehouseStructureExtractIn | None = None,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseStructureExtractOut:
    """Trigger automatic aisle/rack/shelf/bin extraction for the latest map.

    Runs in the warehouse-mapping Celery worker; auto-generated scan targets and
    a STRUCTURE_MAP asset are written when it completes. Re-runnable with
    different bin pitch / standoff / clearance without re-flying.
    """
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    resolved = await resolve_latest_model_flight(db, warehouse_map_id=warehouse_map_id)
    if resolved is None:
        raise HTTPException(
            status_code=409,
            detail="No ready 3D map with a live-map flight is available to extract from.",
        )
    model_id, client_flight_id = resolved
    params_payload = payload.to_params_payload() if payload is not None else {}
    params_payload = await _resolve_template_payload(
        db,
        warehouse_map_id=warehouse_map_id,
        params_payload=params_payload,
    )

    worker_ok, worker_detail = await asyncio.to_thread(warehouse_mapping_worker_ready)
    if not worker_ok:
        raise HTTPException(
            status_code=503,
            detail=worker_detail or "Warehouse mapping worker is not running.",
        )

    task_id: str | None = None
    try:
        durable_job = await create_durable_extraction_job(
            db,
            warehouse_map_id=int(warehouse_map_id),
            model_id=int(model_id),
            client_flight_id=client_flight_id,
            params=params_payload,
        )
        await db.commit()
        task_id = durable_job.processor_task_id
        if task_id is None:
            from backend.infrastructure.jobs import enqueue_task

            task_id = enqueue_task(
                "warehouse_mapping.extract_structure",
                queue=settings.celery_warehouse_mapping_queue,
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                client_flight_id=client_flight_id,
                params=params_payload,
                extraction_job_id=int(durable_job.id),
            )
            await update_durable_extraction_job(
                db,
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                status="queued",
                task_id=task_id,
                job_id=int(durable_job.id),
            )
            await db.commit()
        record_extraction_queued(
            warehouse_map_id=int(warehouse_map_id),
            model_id=int(model_id),
            client_flight_id=client_flight_id,
            task_id=task_id,
            source="api",
        )
    except Exception as exc:
        await db.rollback()
        try:
            await update_durable_extraction_job(
                db,
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                status="failed",
                error=str(exc),
                job_id=int(locals().get("durable_job").id) if locals().get("durable_job") else None,
            )
            await db.commit()
        except Exception:
            await db.rollback()
        logger.exception("warehouse_structure_extraction_enqueue_failed_api")
        raise HTTPException(
            status_code=503,
            detail="Structure extraction worker is unavailable.",
        ) from exc

    logger.info(
        "warehouse_structure_extraction_requested map_id=%s model_id=%s flight=%s task=%s",
        warehouse_map_id,
        model_id,
        client_flight_id,
        task_id,
    )
    return WarehouseStructureExtractOut(
        status="queued",
        warehouse_map_id=int(warehouse_map_id),
        model_id=int(model_id),
        client_flight_id=client_flight_id,
        task_id=task_id,
    )


@router.post(
    "/maps/{warehouse_map_id}/structure/dry-run",
    response_model=WarehouseStructureDryRunOut,
)
async def dry_run_warehouse_structure_endpoint(
    warehouse_map_id: int,
    payload: WarehouseStructureExtractIn | None = None,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseStructureDryRunOut:
    """Run automatic structure detection without mutating layout or targets."""
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    resolved = await resolve_latest_model_flight(db, warehouse_map_id=warehouse_map_id)
    if resolved is None:
        raise HTTPException(
            status_code=409,
            detail="No ready 3D map with a live-map flight is available to extract from.",
        )
    model_id, client_flight_id = resolved
    from backend.modules.warehouse.service.structure_jobs import params_from_payload

    result = await dry_run_structure_extraction(
        warehouse_map_id=int(warehouse_map_id),
        model_id=int(model_id),
        client_flight_id=client_flight_id,
        params=params_from_payload(
            await _resolve_template_payload(
                db,
                warehouse_map_id=warehouse_map_id,
                params_payload=payload.to_params_payload() if payload is not None else {},
            )
        ),
    )
    return WarehouseStructureDryRunOut(**result)


@router.get(
    "/maps/{warehouse_map_id}/structure",
    response_model=WarehouseStructureSummaryOut,
)
async def get_warehouse_structure(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseStructureSummaryOut:
    """Return the most recent detected structure (aisles/racks) for overlays."""
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    asset = (
        await db.execute(
            select(WarehouseAsset)
            .join(WarehouseModel, WarehouseAsset.model_id == WarehouseModel.id)
            .where(
                WarehouseModel.warehouse_map_id == int(warehouse_map_id),
                WarehouseAsset.type == STRUCTURE_ASSET_TYPE,
            )
            .order_by(WarehouseAsset.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if asset is None:
        task_state = get_extraction_state(warehouse_map_id) or {}
        if not task_state:
            task_state = await get_durable_extraction_state(db, warehouse_map_id) or {}
        if not task_state:
            resolved = await resolve_latest_model_flight(db, warehouse_map_id=warehouse_map_id)
            if resolved is not None:
                model_id, client_flight_id = resolved
                task_state = {
                    "status": "not_started",
                    "model_id": int(model_id),
                    "client_flight_id": client_flight_id,
                }
        raw_status = str(task_state.get("status") or "not_started")
        structure_status: Literal["not_started", "queued", "running", "ready", "needs_review", "failed"]
        if raw_status == "queued":
            structure_status = "queued"
        elif raw_status in {"running", "processing"}:
            structure_status = "running"
        elif raw_status == "ready":
            structure_status = "ready"
        elif raw_status == "failed":
            structure_status = "failed"
        else:
            structure_status = "not_started"
        return WarehouseStructureSummaryOut(
            status=structure_status,
            warehouse_map_id=int(warehouse_map_id),
            model_id=task_state.get("model_id"),
            client_flight_id=task_state.get("client_flight_id"),
            task_id=task_state.get("task_id"),
            error_message=task_state.get("error_message"),
            failure_reason_codes=list(task_state.get("failure_reason_codes") or []),
            debug_artifact_url=task_state.get("debug_artifact_url"),
            target_count=0,
            active_target_count=0,
            summary={},
        )
    meta = asset.meta_data if isinstance(asset.meta_data, dict) else {}
    summary = meta.get("summary")
    summary_dict = summary if isinstance(summary, dict) else {}
    ensure_structure_quality_summary(summary_dict)
    quality = summary_dict.get("quality") if isinstance(summary_dict, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    quality_status = str(meta.get("quality_status") or quality.get("status") or "ready")
    if quality_status not in {"ready", "needs_review", "failed"}:
        quality_status = "needs_review"
    return WarehouseStructureSummaryOut(
        status=quality_status,  # type: ignore[arg-type]
        warehouse_map_id=int(warehouse_map_id),
        model_id=int(asset.model_id),
        generated_at=meta.get("generated_at"),
        target_count=int(meta.get("target_count") or 0),
        active_target_count=int(
            meta.get(
                "active_target_count",
                int(meta.get("target_count") or 0) if quality_status == "ready" else 0,
            )
            or 0
        ),
        review_target_count=int(meta.get("review_target_count") or 0),
        rejected_target_count=int(meta.get("rejected_target_count") or 0),
        coordinate_setup_status=str(
            meta.get("coordinate_setup_status")
            or summary_dict.get("coordinate_setup_status")
            or ("active" if quality_status == "ready" else "draft")
        ),  # type: ignore[arg-type]
        manual_review_required=bool(
            meta.get("manual_review_required", quality_status != "ready")
        ),
        target_counts=(
            dict(summary_dict.get("target_counts") or {})
            if isinstance(summary_dict.get("target_counts"), dict)
            else {}
        ),
        quality_status=quality_status,  # type: ignore[arg-type]
        quality_reasons=list(meta.get("quality_reasons") or quality.get("reasons") or []),
        failure_reason_codes=list(
            meta.get("failure_reason_codes")
            or summary_dict.get("failure_reason_codes")
            or quality.get("reasons")
            or []
        ),
        debug_artifact_url=meta.get("debug_artifact_url"),
        debug_artifact_path=meta.get("debug_artifact_path"),
        confidence=meta.get("confidence") if meta.get("confidence") is not None else quality.get("confidence"),
        summary=summary_dict,
    )
