from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import require_admin
from backend.db.models import ExportJob, MappingJob, Organization, User, UserRole
from backend.db.session import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


async def _get_db():
    async with Session() as s:
        yield s


@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(_get_db),
):
    offset = (page - 1) * page_size
    q = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = q.scalars().all()
    total_q = await db.execute(select(func.count()).select_from(User))
    total = total_q.scalar_one()
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "role": u.role.value if hasattr(u.role, "value") else str(u.role),
                "org_id": u.org_id,
                "full_name": u.full_name,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(_get_db),
):
    role_str = body.get("role")
    try:
        role = UserRole(role_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role_str}")

    await db.execute(update(User).where(User.id == user_id).values(role=role))
    await db.commit()
    return {"ok": True}


@router.get("/organizations")
async def list_organizations(db: AsyncSession = Depends(_get_db)):
    q = await db.execute(
        select(
            Organization.id,
            Organization.name,
            Organization.slug,
            Organization.created_at,
            func.count(User.id).label("user_count"),
        )
        .outerjoin(User, User.org_id == Organization.id)
        .group_by(Organization.id)
        .order_by(Organization.created_at.desc())
    )
    rows = q.all()
    return {
        "organizations": [
            {
                "id": r.id,
                "name": r.name,
                "slug": r.slug,
                "user_count": r.user_count,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/mapping-jobs")
async def list_mapping_jobs(
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(_get_db),
):
    offset = (page - 1) * page_size
    stmt = (
        select(MappingJob).order_by(MappingJob.created_at.desc()).offset(offset).limit(page_size)
    )
    if status:
        stmt = stmt.where(MappingJob.status == status)
    q = await db.execute(stmt)
    jobs = q.scalars().all()
    return {
        "jobs": [
            {
                "id": j.id,
                "field_id": j.field_id,
                "status": j.status,
                "progress": j.progress,
                "processor": j.processor,
                "error": j.error,
                "created_at": j.created_at.isoformat(),
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in jobs
        ]
    }


@router.post("/mapping-jobs/{job_id}/requeue")
async def requeue_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(_get_db),
):
    from backend.tasks.photogrammetry_tasks import run_photogrammetry_pipeline

    q = await db.execute(select(MappingJob).where(MappingJob.id == job_id))
    job = q.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("failed", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot requeue job with status: {job.status}")

    await db.execute(
        update(MappingJob)
        .where(MappingJob.id == job_id)
        .values(status="pending", error=None, progress=0)
    )
    await db.commit()
    run_photogrammetry_pipeline.delay(job_id)
    return {"ok": True, "job_id": job_id}


@router.get("/export-jobs")
async def list_export_jobs(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(_get_db),
):
    offset = (page - 1) * page_size
    q = await db.execute(
        select(ExportJob).order_by(ExportJob.created_at.desc()).offset(offset).limit(page_size)
    )
    jobs = q.scalars().all()
    return {
        "jobs": [
            {
                "id": j.id,
                "org_id": j.org_id,
                "flight_id": j.flight_id,
                "status": j.status,
                "download_url": j.download_url,
                "created_at": j.created_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "error": j.error,
            }
            for j in jobs
        ]
    }


@router.get("/worker-health")
async def worker_health():
    try:
        from backend.tasks.celery_app import celery_app

        inspect = celery_app.control.inspect(timeout=3.0)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        return {
            "workers": list(active.keys()),
            "active_tasks": {w: len(tasks) for w, tasks in active.items()},
            "reserved_tasks": {w: len(tasks) for w, tasks in reserved.items()},
            "total_active": sum(len(t) for t in active.values()),
        }
    except Exception as exc:
        return {"error": str(exc), "workers": [], "total_active": 0}
