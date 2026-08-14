from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import require_user
from backend.modules.property_patrol import repository as property_patrol_repository
from backend.modules.property_patrol.api.route_support import get_site, validate_site_payload
from backend.modules.property_patrol.models import PropertyPatrolSite
from backend.modules.property_patrol.schemas import (
    PropertyPatrolSiteCreate,
    PropertyPatrolSiteOut,
    PropertyPatrolSiteUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["property-patrol"])
AsyncSession = Any


@router.get("/sites", response_model=Page[PropertyPatrolSiteOut])
async def list_sites(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await property_patrol_repository.list_sites(
        db, limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        [PropertyPatrolSiteOut.model_validate(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
    )


@router.post("/sites", response_model=PropertyPatrolSiteOut)
async def create_site(
    payload: PropertyPatrolSiteCreate,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    validate_site_payload(payload)
    site = PropertyPatrolSite(
        owner_id=getattr(user, "id", None),
        org_id=getattr(user, "org_id", None),
        **payload.model_dump(mode="json"),
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    logger.info("property_patrol_site_created", extra={"site_id": site.id})
    return site


@router.get("/sites/{site_id}", response_model=PropertyPatrolSiteOut)
async def get_site_route(site_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await get_site(db, site_id, user)


@router.patch("/sites/{site_id}", response_model=PropertyPatrolSiteOut)
async def update_site(
    site_id: int,
    payload: PropertyPatrolSiteUpdate,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    validate_site_payload(payload)
    site = await get_site(db, site_id, user)
    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(site, key, value)
    await db.commit()
    await db.refresh(site)
    return site


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    site = await get_site(db, site_id, user)
    await db.delete(site)
    await db.commit()
