from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.schemas import (
    PlanPreviewOut,
    PlanPreviewRequest,
    AgriculturePlanIn,
    AgriculturePlanOut,
    AgricultureGridUpdateIn,
    AgriculturePreflightIn,
    AgriculturePreflightAcknowledgeIn,
    AgriculturePreflightOut,
)
from backend.modules.agriculture.service import agriculture_service
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.missions.schemas.mission_create import MissionCreateIn, MissionCreateOut
from backend.modules.missions.service.mission_start import start_mission_for_user
from backend.modules.agriculture.workflow import create_plan, snapshot_is_usable, update_plan_grid
from backend.modules.agriculture.preflight_service import evaluate_server_preflight
from backend.modules.agriculture.workflow_models import (
    AgricultureMissionPlan,
    AgricultureMissionPlanRevision,
    AgriculturePreflightSnapshot,
)

from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.routers.common import (
    _plan_out,
    _preflight_out,
)

router = APIRouter()


@router.post("/flights/plan-preview", response_model=PlanPreviewOut)
async def plan_preview(payload: PlanPreviewRequest, org_user: OrgUser = Depends(require_org_user), db: AsyncSession = Depends(get_db)):
    if payload.field_id is not None:
        await _common._owned_field(payload.field_id, org_user, db)
    try:
        return await agriculture_service.preview(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/flights/plans", response_model=AgriculturePlanOut, status_code=201)
async def create_agriculture_plan(payload: AgriculturePlanIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(payload.field_id, org_user, db)
    try:
        plan = await create_plan(
            db,
            payload=payload,
            org_id=getattr(org_user.user, "org_id", None),
            user_id=getattr(org_user.user, "id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "AGRICULTURE_PLAN_INVALID", "message": str(exc)}) from exc
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan)


@router.get("/flights/plans/{plan_id}", response_model=AgriculturePlanOut)
async def get_agriculture_plan(plan_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    plan = await db.scalar(select(AgricultureMissionPlan).where(AgricultureMissionPlan.id == plan_id))
    if plan is None or (plan.org_id is not None and plan.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture mission plan not found")
    return _plan_out(plan)


@router.post("/flights/plans/{plan_id}/validate", response_model=AgriculturePlanOut)
async def validate_agriculture_plan(plan_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    plan = await db.scalar(select(AgricultureMissionPlan).where(AgricultureMissionPlan.id == plan_id))
    if plan is None or (plan.org_id is not None and plan.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture mission plan not found")
    plan.status = "validated" if not plan.validation_errors_json else "invalid"
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan)


@router.get("/flights/plans/{plan_id}/grid-revisions", response_model=list[dict[str, Any]])
async def list_agriculture_grid_revisions(plan_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    plan = await db.scalar(select(AgricultureMissionPlan).where(AgricultureMissionPlan.id == plan_id))
    if plan is None or (plan.org_id is not None and plan.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture mission plan not found")
    revisions = list((await db.scalars(select(AgricultureMissionPlanRevision).where(AgricultureMissionPlanRevision.plan_id == plan_id).order_by(AgricultureMissionPlanRevision.revision.desc()))).all())
    return [{"id": row.id, "plan_id": row.plan_id, "revision": row.revision, "planner_version": row.planner_version, "snapshot": row.snapshot_json, "grid_geojson": row.grid_geojson, "estimates": row.estimates_json, "created_at": row.created_at} for row in revisions]


@router.put("/flights/plans/{plan_id}/grid", response_model=AgriculturePlanOut)
async def update_agriculture_plan_grid(plan_id: str, payload: AgricultureGridUpdateIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    plan = await db.scalar(select(AgricultureMissionPlan).where(AgricultureMissionPlan.id == plan_id))
    if plan is None or (plan.org_id is not None and plan.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture mission plan not found")
    try:
        revision = update_plan_grid(plan, payload, user_id=getattr(org_user.user, "id", None))
    except ValueError as exc:
        code = "AGRICULTURE_GRID_REVISION_CONFLICT" if str(exc) == "AGRICULTURE_GRID_REVISION_CONFLICT" else "AGRICULTURE_GRID_INVALID"
        raise HTTPException(status_code=409 if code.endswith("CONFLICT") else 422, detail={"code": code, "message": str(exc)}) from exc
    db.add(revision)
    await db.execute(
        update(AgriculturePreflightSnapshot)
        .where(AgriculturePreflightSnapshot.plan_id == plan.id, AgriculturePreflightSnapshot.status == "pass")
        .values(status="expired")
    )
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan)


@router.post("/flights/plans/{plan_id}/duplicate", response_model=AgriculturePlanOut, status_code=201)
async def duplicate_agriculture_plan(plan_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    source = await db.scalar(select(AgricultureMissionPlan).where(AgricultureMissionPlan.id == plan_id))
    if source is None or (source.org_id is not None and source.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture mission plan not found")
    payload = AgriculturePlanIn.model_validate(source.payload_json)
    plan = await create_plan(db, payload=payload, org_id=source.org_id, user_id=getattr(org_user.user, "id", None), source_plan_id=source.id)
    # Repeat missions always start as a fresh draft that must pass current validation/preflight.
    plan.status = "draft"
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan)


@router.post("/flights/plans/{plan_id}/replan", response_model=AgriculturePlanOut, status_code=201)
async def replan_agriculture_flight(plan_id: str, payload: AgriculturePlanIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    source = await db.scalar(select(AgricultureMissionPlan).where(AgricultureMissionPlan.id == plan_id))
    if source is None or source.field_id != payload.field_id or (source.org_id is not None and source.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture mission plan not found")
    source.status = "superseded"
    plan = await create_plan(db, payload=payload, org_id=source.org_id, user_id=getattr(org_user.user, "id", None), source_plan_id=source.id)
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan)


@router.post("/flights/plans/{plan_id}/preflight", response_model=AgriculturePreflightOut, status_code=201)
async def evaluate_agriculture_preflight(plan_id: str, payload: AgriculturePreflightIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    plan = await db.scalar(select(AgricultureMissionPlan).where(AgricultureMissionPlan.id == plan_id))
    if plan is None or (plan.org_id is not None and plan.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture mission plan not found")
    snapshot = await evaluate_server_preflight(db, plan=plan, user=org_user)
    snapshot.operator_notes = payload.notes
    await db.commit()
    await db.refresh(snapshot)
    return _preflight_out(snapshot)


@router.get("/preflight/{snapshot_id}", response_model=AgriculturePreflightOut)
async def get_agriculture_preflight(snapshot_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    snapshot = await db.scalar(select(AgriculturePreflightSnapshot).where(AgriculturePreflightSnapshot.id == snapshot_id))
    if snapshot is None or (snapshot.org_id is not None and snapshot.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture preflight snapshot not found")
    return _preflight_out(snapshot)


@router.post("/preflight/{snapshot_id}/acknowledge", response_model=AgriculturePreflightOut)
async def acknowledge_agriculture_preflight(snapshot_id: str, payload: AgriculturePreflightAcknowledgeIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    snapshot = await db.scalar(select(AgriculturePreflightSnapshot).where(AgriculturePreflightSnapshot.id == snapshot_id))
    if snapshot is None or (snapshot.org_id is not None and snapshot.org_id != getattr(org_user.user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Agriculture preflight snapshot not found")
    if not payload.operator_confirmed or not snapshot_is_usable(snapshot):
        raise HTTPException(status_code=412, detail={"code": "AGRICULTURE_PREFLIGHT_BLOCKED", "message": "All blocking agriculture checks must pass before acknowledgement"})
    snapshot.acknowledged_by_user_id = getattr(org_user.user, "id", None)
    snapshot.acknowledged_at = datetime.now(UTC)
    snapshot.signoff_hash = hashlib.sha256(f"{snapshot.fingerprint}:{snapshot.acknowledged_by_user_id}:{snapshot.acknowledged_at.isoformat()}".encode()).hexdigest()
    await db.commit()
    await db.refresh(snapshot)
    return _preflight_out(snapshot)


@router.post("/flights/start", response_model=MissionCreateOut, status_code=202)
async def start_agriculture_flight(
    payload: MissionCreateIn,
    org_user: OrgUser = Depends(require_org_user),
):
    if payload.field_id is None or payload.agriculture is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "AGRICULTURE_CONTEXT_REQUIRED", "message": "field_id and agriculture profile are required"},
        )
    return await start_mission_for_user(payload, user=org_user.user)

