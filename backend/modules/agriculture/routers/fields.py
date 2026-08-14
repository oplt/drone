from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping

from backend.core.database.session import get_db
from backend.modules.agriculture.models import (
    AgricultureFieldProfile,
    AgricultureFlight,
)
from backend.modules.agriculture.p4_models import (
    AgricultureHarvestLabel,
)
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.schemas import (
    AgricultureFieldProfileOut,
    AgricultureFlightOut,
    FieldProfilePatch,
    HarvestLabelIn,
    HarvestLabelOut,
    AgriculturePlanOut,
)
from backend.modules.agriculture.service import agriculture_service, utc
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.fields.service import field_service
from backend.modules.agriculture.workflow_models import (
    AgricultureMissionPlan,
)

from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.routers.common import (
    _plan_out,
    _profile_out,
)

router = APIRouter()


@router.get("/fields/overview", response_model=list[dict[str, Any]])
async def agriculture_field_overview(db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    fields = await field_service.list_owned(db, user=org_user.user, query=None, limit=500, workflow_scope=None)
    output = []
    for field in fields:
        if field.workflow_scope not in {"agriculture", "field_survey"}:
            continue
        profile = await db.scalar(select(AgricultureFieldProfile).where(AgricultureFieldProfile.field_id == field.id))
        latest = await db.scalar(select(AgricultureFlight).where(AgricultureFlight.field_id == field.id).order_by(AgricultureFlight.created_at.desc()).limit(1))
        output.append({"id": field.id, "name": field.name, "area_ha": field.area_ha, "workflow_scope": field.workflow_scope, "geometry_geojson": mapping(to_shape(field.boundary)) if getattr(field, "boundary", None) is not None else {}, "profile": {"crop_type": profile.crop_type, "variety": profile.variety, "season": profile.season, "growth_stage": profile.growth_stage} if profile else {}, "latest_flight": {"id": latest.id, "status": latest.status, "created_at": latest.created_at, "quality_summary": latest.quality_summary or {}, "coverage_summary": latest.coverage_summary or {}} if latest else None})
    return output


@router.get("/fields/{field_id}/profile", response_model=AgricultureFieldProfileOut)
async def get_field_profile(field_id: int, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    return _profile_out(await agriculture_service.get_or_create_profile(db, field_id=field_id, user=org_user.user))


@router.post("/fields/{field_id}/harvest-labels", response_model=HarvestLabelOut, status_code=201)
async def register_harvest_label(field_id: int, payload: HarvestLabelIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    record = AgricultureHarvestLabel(field_id=field_id, org_id=getattr(org_user.user, "org_id", None), created_by_user_id=getattr(org_user.user, "id", None), harvest_date=utc(payload.harvest_date), crop_type=payload.crop_type, variety=payload.variety, yield_value=payload.yield_value, yield_unit=payload.yield_unit, area_ha=payload.area_ha, source=payload.source, quality=payload.quality, metadata_json=payload.metadata)
    db.add(record); await db.commit(); await db.refresh(record)
    return {"id": record.id, "field_id": record.field_id, "harvest_date": record.harvest_date, "crop_type": record.crop_type, "variety": record.variety, "yield_value": record.yield_value, "yield_unit": record.yield_unit, "area_ha": record.area_ha, "source": record.source, "quality": record.quality, "metadata": record.metadata_json}


@router.get("/fields/{field_id}/harvest-labels", response_model=list[HarvestLabelOut])
async def list_harvest_labels(field_id: int, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    rows = list((await db.scalars(select(AgricultureHarvestLabel).where(AgricultureHarvestLabel.field_id == field_id).order_by(AgricultureHarvestLabel.harvest_date.desc()))).all())
    return [{"id": row.id, "field_id": row.field_id, "harvest_date": row.harvest_date, "crop_type": row.crop_type, "variety": row.variety, "yield_value": row.yield_value, "yield_unit": row.yield_unit, "area_ha": row.area_ha, "source": row.source, "quality": row.quality, "metadata": row.metadata_json} for row in rows]


@router.patch("/fields/{field_id}/profile", response_model=AgricultureFieldProfileOut)
async def patch_field_profile(field_id: int, payload: FieldProfilePatch, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    return _profile_out(await agriculture_service.patch_profile(db, field_id=field_id, user=org_user.user, patch=payload))


@router.get("/fields/{field_id}/plans", response_model=list[AgriculturePlanOut])
async def list_field_plans(field_id: int, limit: int = Query(25, ge=1, le=100), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    rows = list(
        (
            await db.scalars(
                select(AgricultureMissionPlan)
                .where(
                    AgricultureMissionPlan.field_id == field_id,
                    AgricultureMissionPlan.status.in_(["draft", "validated", "committed", "invalid"]),
                )
                .order_by(AgricultureMissionPlan.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return [_plan_out(row) for row in rows]


@router.get("/fields/{field_id}/flights", response_model=list[AgricultureFlightOut])
async def list_field_flights(field_id: int, limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    return await agriculture_repository.list_flights(db, field_id=field_id, user=org_user.user, limit=limit)


@router.get("/fields/{field_id}/timeline", response_model=list[AgricultureFlightOut])
async def field_timeline(field_id: int, limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    return await agriculture_repository.list_flights(db, field_id=field_id, user=org_user.user, limit=limit)

