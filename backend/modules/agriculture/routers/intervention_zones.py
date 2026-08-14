from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.intervention_models import AgricultureInterventionZone
from backend.modules.agriculture.intervention_schemas import (
    InterventionZoneApprovalIn,
    InterventionZoneCreateIn,
    InterventionZoneOut,
    InterventionZoneUpdateIn,
)
from backend.modules.agriculture.intervention_service import (
    InterventionZoneConflict,
    agriculture_intervention_zone_service,
)
from backend.modules.agriculture.p5_models import AgricultureGovernanceAudit
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.routers import common as _common
from backend.modules.identity.dependencies import OrgUser, require_org_user

router = APIRouter()


async def _owned_zone(
    zone_id: str, org_user: OrgUser, db: AsyncSession, *, for_update: bool = False
) -> AgricultureInterventionZone:
    statement = select(AgricultureInterventionZone).where(AgricultureInterventionZone.id == zone_id)
    zone = await db.scalar(statement.with_for_update() if for_update else statement)
    if (
        zone is None
        or await agriculture_repository.get_run(db, run_id=zone.run_id, user=org_user.user) is None
    ):
        raise HTTPException(status_code=404, detail="Intervention zone not found")
    return zone


def _zone_error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=409 if isinstance(exc, InterventionZoneConflict) else 422, detail=str(exc)
    )


@router.post(
    "/analysis-runs/{run_id}/intervention-zones",
    response_model=InterventionZoneOut,
    status_code=201,
)
async def create_intervention_zone(
    run_id: str,
    payload: InterventionZoneCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    field = await _common._owned_field(flight.field_id, org_user, db)
    try:
        return await agriculture_intervention_zone_service.create(
            db,
            run=run,
            flight=flight,
            field=field,
            name=payload.name,
            category=payload.category,
            observation_ids=payload.source_observation_ids,
            user_id=getattr(org_user.user, "id", None),
            org_id=getattr(org_user.user, "org_id", None),
        )
    except ValueError as exc:
        raise _zone_error(exc) from exc


@router.get("/analysis-runs/{run_id}/intervention-zones", response_model=list[InterventionZoneOut])
async def list_intervention_zones(
    run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)
):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list(
        (
            await db.scalars(
                select(AgricultureInterventionZone)
                .where(AgricultureInterventionZone.run_id == run.id)
                .order_by(AgricultureInterventionZone.created_at.desc())
            )
        ).all()
    )


@router.put("/intervention-zones/{zone_id}", response_model=InterventionZoneOut)
async def update_intervention_zone(
    zone_id: str,
    payload: InterventionZoneUpdateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    zone = await _owned_zone(zone_id, org_user, db, for_update=True)
    field = await _common._owned_field(zone.field_id, org_user, db)
    try:
        return await agriculture_intervention_zone_service.update(
            db,
            zone=zone,
            field=field,
            values=payload.model_dump(exclude_unset=True),
            user_id=getattr(org_user.user, "id", None),
        )
    except ValueError as exc:
        raise _zone_error(exc) from exc


@router.post("/intervention-zones/{zone_id}/approval", response_model=InterventionZoneOut)
async def review_intervention_zone(
    zone_id: str,
    payload: InterventionZoneApprovalIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    zone = await _owned_zone(zone_id, org_user, db, for_update=True)
    try:
        return await agriculture_intervention_zone_service.review(
            db,
            zone=zone,
            status=payload.status,
            note=payload.note,
            expected_revision=payload.expected_revision,
            user_id=getattr(org_user.user, "id", None),
        )
    except ValueError as exc:
        raise _zone_error(exc) from exc


@router.get("/intervention-zones/{zone_id}/audit", response_model=list[dict[str, Any]])
async def intervention_zone_audit(
    zone_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)
):
    zone = await _owned_zone(zone_id, org_user, db)
    rows = list(
        (
            await db.scalars(
                select(AgricultureGovernanceAudit)
                .where(
                    AgricultureGovernanceAudit.entity_type == "intervention_zone",
                    AgricultureGovernanceAudit.entity_id == zone.id,
                )
                .order_by(AgricultureGovernanceAudit.created_at.asc())
            )
        ).all()
    )
    return [
        {
            "id": row.id,
            "actor_user_id": row.actor_user_id,
            "action": row.action,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "reason": row.reason,
            "payload": row.payload,
            "created_at": row.created_at,
        }
        for row in rows
    ]
