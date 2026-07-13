from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.irrigation.models import IrrigationProcessingJob


class IrrigationJobRepository:
    async def recover_stale_running(
        self,
        db: AsyncSession,
        *,
        stale_after_s: float,
    ) -> int:
        """Requeue jobs whose worker disappeared before terminal persistence."""
        cutoff = datetime.now(UTC) - timedelta(seconds=max(1.0, stale_after_s))
        result: Any = await db.execute(
            update(IrrigationProcessingJob)
            .where(
                IrrigationProcessingJob.status == "running",
                IrrigationProcessingJob.started_at.is_not(None),
                IrrigationProcessingJob.started_at < cutoff,
            )
            .values(
                status="queued",
                celery_task_id=None,
                error="Worker lease expired; job requeued",
                started_at=None,
            )
        )
        await db.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def create(
        self,
        db: AsyncSession,
        *,
        job_id: str,
        mission_id: str,
        org_id: int | None,
        user_id: int | None,
        input_checksum: str,
        force: bool = False,
    ) -> IrrigationProcessingJob:
        job = IrrigationProcessingJob(
            id=job_id,
            mission_id=mission_id,
            org_id=org_id,
            requested_by_user_id=user_id,
            input_checksum=input_checksum,
            force=force,
            status="queued",
        )
        db.add(job)
        await db.flush()
        return job

    async def find_reusable(
        self,
        db: AsyncSession,
        *,
        mission_id: str,
        input_checksum: str,
        force: bool,
    ) -> IrrigationProcessingJob | None:
        statuses = ("queued", "running") if force else ("queued", "running", "completed")
        return cast(IrrigationProcessingJob | None, await db.scalar(
            select(IrrigationProcessingJob)
            .where(
                IrrigationProcessingJob.mission_id == mission_id,
                IrrigationProcessingJob.input_checksum == input_checksum,
                IrrigationProcessingJob.status.in_(statuses),
            )
            .order_by(IrrigationProcessingJob.created_at.desc())
            .limit(1)
        ))

    async def get_owned(
        self, db: AsyncSession, *, job_id: str, org_id: int | None
    ) -> IrrigationProcessingJob | None:
        return cast(IrrigationProcessingJob | None, await db.scalar(
            select(IrrigationProcessingJob).where(
                IrrigationProcessingJob.id == job_id,
                IrrigationProcessingJob.org_id == org_id,
            )
        ))

    async def mark_started(self, db: AsyncSession, job_id: str) -> None:
        await db.execute(
            update(IrrigationProcessingJob)
            .where(IrrigationProcessingJob.id == job_id)
            .values(
                status="running",
                started_at=datetime.now(UTC),
                completed_at=None,
                error=None,
            )
        )
        await db.commit()

    async def mark_retrying(self, db: AsyncSession, job_id: str, *, error: str) -> None:
        await db.execute(
            update(IrrigationProcessingJob)
            .where(IrrigationProcessingJob.id == job_id)
            .values(status="queued", error=error, completed_at=None)
        )
        await db.commit()

    async def mark_finished(
        self, db: AsyncSession, job_id: str, *, status: str, error: str | None = None
    ) -> None:
        await db.execute(
            update(IrrigationProcessingJob)
            .where(IrrigationProcessingJob.id == job_id)
            .values(status=status, error=error, completed_at=datetime.now(UTC))
        )
        await db.commit()
