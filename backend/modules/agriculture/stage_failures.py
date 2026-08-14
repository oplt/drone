"""Persistence for retryable and terminal agriculture stage failures."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.agriculture.lifecycle import append_analysis_event
from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureAnalysisStage
from backend.modules.agriculture.repository import agriculture_repository


async def record_stage_failure(
    run_id: str,
    stage_name: str,
    *,
    status: str,
    error: str | None,
    dead_letter: bool,
    task_id: str | None,
    retryable: bool,
) -> None:
    """Persist a Celery delivery failure without obscuring the original error."""
    async with Session() as db:
        stage = await db.scalar(
            select(AgricultureAnalysisStage)
            .where(
                AgricultureAnalysisStage.run_id == run_id,
                AgricultureAnalysisStage.stage_name == stage_name,
            )
            .with_for_update()
        )
        if stage is None:
            stage = AgricultureAnalysisStage(run_id=run_id, stage_name=stage_name)
            db.add(stage)
        now = datetime.now(UTC)
        stage.status = status
        stage.task_id = task_id
        stage.error = error[:4000] if error else None
        stage.retryable = retryable
        stage.dead_letter = dead_letter
        if error:
            stage.last_error_at = now
        if dead_letter:
            stage.dead_letter_at = now

        run = await db.get(AgricultureAnalysisRun, run_id)
        flight = (
            await agriculture_repository.get_flight(db, flight_id=run.flight_id)
            if run is not None
            else None
        )
        if run is not None and flight is not None:
            await append_analysis_event(
                db,
                run=run,
                flight=flight,
                event_type=("stage.retryable" if status == "retrying" else "stage.failed"),
                payload={
                    "stage": stage_name,
                    "status": status,
                    "retryable": retryable,
                    "dead_letter": dead_letter,
                    "error": error[:1000] if error else None,
                },
                dedupe_key=(f"analysis:{run_id}:{stage_name}:{status}:a{stage.attempt}"),
            )
        await db.commit()
