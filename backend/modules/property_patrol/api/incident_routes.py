from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import require_user
from backend.modules.property_patrol import repository as property_patrol_repository
from backend.modules.property_patrol.api.route_support import incident_status
from backend.modules.property_patrol.models import PropertyPatrolIncident
from backend.modules.property_patrol.schemas import IncidentCreate, IncidentOut, IncidentUpdate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["property-patrol"])
AsyncSession = Any


@router.get("/incidents", response_model=Page[IncidentOut])
async def list_incidents(
    site_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await property_patrol_repository.list_incidents(
        db, site_id=site_id, limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        [IncidentOut.model_validate(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
    )


@router.post("/incidents", response_model=IncidentOut)
async def create_incident(
    payload: IncidentCreate, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    incident = PropertyPatrolIncident(**payload.model_dump(mode="json"))
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    logger.info("property_patrol_incident_created", extra={"incident_id": incident.id})
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await property_patrol_repository.get_incident(db, incident_id)


@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: int,
    payload: IncidentUpdate,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    incident = await property_patrol_repository.get_incident(db, incident_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(incident, key, value)
    await db.commit()
    await db.refresh(incident)
    return incident


@router.post("/incidents/{incident_id}/acknowledge", response_model=IncidentOut)
async def acknowledge_incident(
    incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await incident_status(incident_id, "acknowledged", db)


@router.post("/incidents/{incident_id}/mark-false-positive", response_model=IncidentOut)
async def false_positive_incident(
    incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await incident_status(incident_id, "false_positive", db)


@router.post("/incidents/{incident_id}/close", response_model=IncidentOut)
async def close_incident(
    incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await incident_status(incident_id, "closed", db)
