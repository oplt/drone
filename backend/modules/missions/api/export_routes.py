from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.infrastructure.jobs import enqueue_task
from backend.modules.deliverables.service import mission_export_service
from backend.modules.identity.dependencies import require_user

router = APIRouter(tags=["tasks"])


@router.post("/missions/{flight_id}/export")
async def start_mission_export(
    flight_id: str,
    user=Depends(require_user),
):
    job = await mission_export_service.create_for_user(flight_id=flight_id, user=user)
    if job is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    enqueue_task(
        "backend.tasks.export_tasks.generate_mission_export",
        queue="exports",
        flight_id=flight_id,
        user_id=user.id,
        org_id=user.org_id,
        job_id=job.id,
    )
    return {"job_id": job.id}


@router.get("/missions/{flight_id}/export/{job_id}")
async def get_mission_export_status(
    flight_id: str,
    job_id: int,
    user=Depends(require_user),
):
    job = await mission_export_service.get_for_user(flight_id=flight_id, job_id=job_id, user=user)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    return {
        "job_id": job.id,
        "status": job.status,
        "download_url": job.download_url,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
