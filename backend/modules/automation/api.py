from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import Session
from backend.modules.automation.models import MissionTemplate, ScheduledRun
from backend.modules.identity.dependencies import OrgUser, require_org_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    name: str
    mission_type: str
    config: dict = {}
    preflight_profile: dict = {}
    schedule_cron: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    preflight_profile: dict | None = None
    schedule_cron: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]


def _template_dict(t: MissionTemplate) -> dict:
    return {
        "id": t.id,
        "org_id": t.org_id,
        "name": t.name,
        "slug": t.slug,
        "mission_type": t.mission_type,
        "config": t.config,
        "preflight_profile": t.preflight_profile,
        "schedule_cron": t.schedule_cron,
        "is_active": t.is_active,
        "created_by_user_id": t.created_by_user_id,
        "created_at": t.created_at.isoformat(),
    }


def _run_dict(r: ScheduledRun) -> dict:
    return {
        "id": r.id,
        "template_id": r.template_id,
        "triggered_by": r.triggered_by,
        "status": r.status,
        "error": r.error,
        "created_at": r.created_at.isoformat(),
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
    }


async def _get_template_or_404(
    db: AsyncSession, template_id: int, org_id: int | None
) -> MissionTemplate:
    q = await db.execute(select(MissionTemplate).where(MissionTemplate.id == template_id))
    tmpl = q.scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if tmpl.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return tmpl


# ---------------------------------------------------------------------------
# Private DB dependency (matches admin router pattern)
# ---------------------------------------------------------------------------


async def _get_db():
    async with Session() as s:
        yield s


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_templates(
    page: int = 1,
    page_size: int = 20,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(_get_db),
):
    offset = (page - 1) * page_size
    stmt = (
        select(MissionTemplate)
        .where(
            MissionTemplate.org_id == org_user.org_id,
            MissionTemplate.is_active.is_(True),
        )
        .order_by(MissionTemplate.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    q = await db.execute(stmt)
    templates = q.scalars().all()
    return {
        "templates": [_template_dict(t) for t in templates],
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_template(
    body: TemplateCreate,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(_get_db),
):
    base_slug = _make_slug(body.name)
    slug = base_slug
    suffix = 1

    while True:
        tmpl = MissionTemplate(
            org_id=org_user.org_id,
            name=body.name,
            slug=slug,
            mission_type=body.mission_type,
            config=body.config,
            preflight_profile=body.preflight_profile,
            schedule_cron=body.schedule_cron,
            is_active=True,
            created_by_user_id=org_user.user.id,
        )
        db.add(tmpl)
        try:
            await db.commit()
            await db.refresh(tmpl)
            return _template_dict(tmpl)
        except IntegrityError:
            await db.rollback()
            # Slug collision — append numeric suffix and retry
            slug = f"{base_slug[:62]}-{suffix}"
            suffix += 1
            if suffix > 99:
                raise HTTPException(
                    status_code=409, detail="Could not generate unique slug"
                ) from None


@router.get("/{template_id}")
async def get_template(
    template_id: int,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(_get_db),
):
    tmpl = await _get_template_or_404(db, template_id, org_user.org_id)
    return _template_dict(tmpl)


@router.patch("/{template_id}")
async def update_template(
    template_id: int,
    body: TemplateUpdate,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(_get_db),
):
    tmpl = await _get_template_or_404(db, template_id, org_user.org_id)

    if body.name is not None:
        tmpl.name = body.name
    if body.config is not None:
        tmpl.config = body.config
    if body.preflight_profile is not None:
        tmpl.preflight_profile = body.preflight_profile
    if body.schedule_cron is not None:
        tmpl.schedule_cron = body.schedule_cron
    if body.is_active is not None:
        tmpl.is_active = body.is_active

    await db.commit()
    await db.refresh(tmpl)
    return _template_dict(tmpl)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(_get_db),
):
    tmpl = await _get_template_or_404(db, template_id, org_user.org_id)
    tmpl.is_active = False
    await db.commit()


@router.post("/{template_id}/trigger", status_code=202)
async def trigger_template(
    template_id: int,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(_get_db),
):
    from backend.entrypoints.workers.scheduling_tasks import run_template_mission

    tmpl = await _get_template_or_404(db, template_id, org_user.org_id)
    if not tmpl.is_active:
        raise HTTPException(status_code=409, detail="Template is inactive")

    run = ScheduledRun(
        template_id=tmpl.id,
        triggered_by="manual",
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    run_template_mission.delay(run.id)
    logger.info("Manually triggered template %d → scheduled_run %d", tmpl.id, run.id)

    return {"scheduled_run_id": run.id, "status": run.status}


@router.get("/{template_id}/runs")
async def list_template_runs(
    template_id: int,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(_get_db),
):
    # Ownership check
    await _get_template_or_404(db, template_id, org_user.org_id)

    q = await db.execute(
        select(ScheduledRun)
        .where(ScheduledRun.template_id == template_id)
        .order_by(ScheduledRun.created_at.desc())
        .limit(50)
    )
    runs = q.scalars().all()
    return {"runs": [_run_dict(r) for r in runs]}
