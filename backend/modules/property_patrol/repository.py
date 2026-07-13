"""Persistence port for Property Patrol application services."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.property_patrol.models import (
    PropertyPatrolIncident,
    PropertyPatrolRun,
    PropertyPatrolSensorEvent,
    PropertyPatrolSite,
    PropertyPatrolTemplate,
)


async def get_site(db: AsyncSession, site_id: int) -> PropertyPatrolSite:
    site = await db.scalar(select(PropertyPatrolSite).where(PropertyPatrolSite.id == site_id))
    if site is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission site not found")
    return site


async def list_sites(db: AsyncSession, *, limit: int, offset: int) -> list[PropertyPatrolSite]:
    stmt = (
        select(PropertyPatrolSite)
        .order_by(PropertyPatrolSite.updated_at.desc(), PropertyPatrolSite.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.scalars(stmt)).all())


async def get_template(db: AsyncSession, template_id: int) -> PropertyPatrolTemplate:
    template = await db.scalar(
        select(PropertyPatrolTemplate).where(PropertyPatrolTemplate.id == template_id)
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission template not found")
    return template


async def list_templates(
    db: AsyncSession, *, site_id: int | None, limit: int, offset: int
) -> list[PropertyPatrolTemplate]:
    stmt = select(PropertyPatrolTemplate).order_by(
        PropertyPatrolTemplate.updated_at.desc(), PropertyPatrolTemplate.id.desc()
    )
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolTemplate.site_id == site_id)
    return list((await db.scalars(stmt.limit(limit).offset(offset))).all())


async def list_runs(
    db: AsyncSession, *, site_id: int | None, limit: int, offset: int
) -> list[PropertyPatrolRun]:
    stmt = select(PropertyPatrolRun).order_by(
        PropertyPatrolRun.updated_at.desc(), PropertyPatrolRun.id.desc()
    )
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolRun.site_id == site_id)
    return list((await db.scalars(stmt.limit(limit).offset(offset))).all())


async def get_run(db: AsyncSession, mission_run_id: int) -> PropertyPatrolRun:
    run = await db.get(PropertyPatrolRun, mission_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission run not found")
    return run


async def list_sensor_events(
    db: AsyncSession, *, site_id: int | None, limit: int, offset: int
) -> list[PropertyPatrolSensorEvent]:
    stmt = select(PropertyPatrolSensorEvent).order_by(
        PropertyPatrolSensorEvent.created_at.desc(), PropertyPatrolSensorEvent.id.desc()
    )
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolSensorEvent.site_id == site_id)
    return list((await db.scalars(stmt.limit(limit).offset(offset))).all())


async def find_sensor_event(
    db: AsyncSession, *, site_id: int, external_event_id: str
) -> PropertyPatrolSensorEvent | None:
    return await db.scalar(
        select(PropertyPatrolSensorEvent).where(
            PropertyPatrolSensorEvent.site_id == site_id,
            PropertyPatrolSensorEvent.external_event_id == external_event_id,
        )
    )


async def latest_template(db: AsyncSession, *, site_id: int) -> PropertyPatrolTemplate | None:
    return await db.scalar(
        select(PropertyPatrolTemplate)
        .where(PropertyPatrolTemplate.site_id == site_id)
        .order_by(PropertyPatrolTemplate.updated_at.desc())
    )


async def list_incidents(
    db: AsyncSession, *, site_id: int | None, limit: int, offset: int
) -> list[PropertyPatrolIncident]:
    stmt = select(PropertyPatrolIncident).order_by(
        PropertyPatrolIncident.updated_at.desc(), PropertyPatrolIncident.id.desc()
    )
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolIncident.site_id == site_id)
    return list((await db.scalars(stmt.limit(limit).offset(offset))).all())


async def get_incident(db: AsyncSession, incident_id: int) -> PropertyPatrolIncident:
    incident = await db.get(PropertyPatrolIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission incident not found")
    return incident
