from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import require_user
from backend.modules.property_patrol import repository as property_patrol_repository
from backend.modules.property_patrol.api.route_support import get_site, get_template
from backend.modules.property_patrol.models import PropertyPatrolTemplate
from backend.modules.property_patrol.schemas import (
    PatrolTemplateCreate,
    PatrolTemplateOut,
    PatrolTemplateUpdate,
)

router = APIRouter(tags=["property-patrol"])
AsyncSession = Any


@router.get("/templates", response_model=Page[PatrolTemplateOut])
async def list_templates(
    site_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await property_patrol_repository.list_templates(
        db, site_id=site_id, limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        [PatrolTemplateOut.model_validate(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
    )


@router.post("/templates", response_model=PatrolTemplateOut)
async def create_template(
    payload: PatrolTemplateCreate, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    await get_site(db, payload.site_id, user)
    template = PropertyPatrolTemplate(**payload.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/templates/{template_id}", response_model=PatrolTemplateOut)
async def get_template_route(
    template_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await get_template(db, template_id)


@router.patch("/templates/{template_id}", response_model=PatrolTemplateOut)
async def update_template(
    template_id: int,
    payload: PatrolTemplateUpdate,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    template = await get_template(db, template_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    template = await get_template(db, template_id)
    await db.delete(template)
    await db.commit()
