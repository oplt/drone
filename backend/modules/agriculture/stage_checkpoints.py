"""Compatibility checkpoints for agriculture ingest and quality queues."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureAnalysisStage


async def checkpoint_stage(run_id: str, stage_name: str, input_checksum: str) -> dict[str, str]:
    """Persist the original idempotent boundary for non-Phase-6 stages."""
    async with Session() as db:
        run = await db.scalar(
            select(AgricultureAnalysisRun)
            .where(AgricultureAnalysisRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ValueError(f"Agriculture analysis run not found: {run_id}")
        if run.status == "cancelled":
            return {"run_id": run_id, "stage": stage_name, "status": "cancelled"}
        stage = await db.scalar(
            select(AgricultureAnalysisStage)
            .where(
                AgricultureAnalysisStage.run_id == run_id,
                AgricultureAnalysisStage.stage_name == stage_name,
            )
            .with_for_update()
        )
        if stage is not None and stage.status == "completed":
            if stage.input_checksum != input_checksum:
                raise ValueError("Completed stage checksum conflicts with replay input")
            return {"run_id": run_id, "stage": stage_name, "status": "completed"}
        if stage is None:
            stage = AgricultureAnalysisStage(run_id=run_id, stage_name=stage_name)
            db.add(stage)
        stage.input_checksum = input_checksum
        stage.status = "running"
        stage.progress = 0.0
        stage.error = None
        stage.dead_letter = False
        stage.retryable = True
        stage.started_at = datetime.now(UTC)
        await db.flush()
        stage.status = "completed"
        stage.attempt += 1
        stage.progress = 100.0
        stage.finished_at = datetime.now(UTC)
        stage.metrics = {**(stage.metrics or {}), "worker_boundary": stage_name}
        await db.commit()
        return {"run_id": run_id, "stage": stage_name, "status": "completed"}
