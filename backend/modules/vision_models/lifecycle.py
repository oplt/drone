from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.vision_models.models import TrainingRun, VisionProject
from backend.modules.workflow_events.service import append_workflow_event

TRAINING_EVENT_DOMAIN = "vision_training"


async def append_training_event(
    db: AsyncSession,
    *,
    run: TrainingRun,
    project: VisionProject,
    event_type: str,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> None:
    await append_workflow_event(
        db,
        domain=TRAINING_EVENT_DOMAIN,
        stream_id=project.id,
        subject_id=run.id,
        event_type=event_type,
        org_id=project.org_id,
        user_id=getattr(run, "created_by_user_id", None),
        payload={"run_id": run.id, "project_id": project.id, **(payload or {})},
        dedupe_key=dedupe_key,
    )


async def append_training_status_event(
    db: AsyncSession,
    run: TrainingRun,
    event_type: str,
    key: str,
    payload: dict[str, Any] | None = None,
    *,
    project: VisionProject | None = None,
) -> None:
    """Append a training event with a consistent lifecycle envelope."""
    project = project or await db.get(VisionProject, run.project_id)
    if project is None:
        return
    await append_training_event(
        db,
        run=run,
        project=project,
        event_type=event_type,
        payload={
            "status": run.status,
            "progress": run.progress,
            "epoch": run.current_epoch,
            "total_epochs": run.epochs,
            **(payload or {}),
        },
        dedupe_key=f"training:{run.id}:{key}",
    )
