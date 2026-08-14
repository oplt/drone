"""Completion-triggered wakeups and safety reconciliation for RGB dependencies."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.agriculture.analysis_orchestration import (
    agriculture_analysis_orchestration,
)
from backend.modules.agriculture.lifecycle import append_analysis_event
from backend.modules.agriculture.models import (
    AgricultureAnalysisRun,
    AgricultureAnalysisStage,
    AgricultureAnalysisVideoJob,
)
from backend.modules.agriculture.queue import agriculture_analysis_queue
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.stage_operations import stage_input_checksum


def _rgb_delivery(run: AgricultureAnalysisRun) -> tuple[str, float]:
    radius = float((run.counters or {}).get("cluster_radius_m", 8.0))
    checksum = stage_input_checksum(
        run,
        "rgb_inference",
        extra={"cluster_radius_m": radius},
    )
    return checksum, radius


async def resume_runs_for_video_job(job_id: str, status: str) -> dict[str, int]:
    """Wake waiting RGB coordinators once per terminal dependency signal."""
    pending: list[tuple[str, str, float]] = []
    async with Session() as db:
        run_ids = list(
            (
                await db.scalars(
                    select(AgricultureAnalysisVideoJob.run_id)
                    .where(AgricultureAnalysisVideoJob.video_job_id == job_id)
                    .distinct()
                )
            ).all()
        )
        for run_id in run_ids:
            run = await db.scalar(
                select(AgricultureAnalysisRun)
                .where(AgricultureAnalysisRun.id == run_id)
                .with_for_update()
            )
            if run is None or run.status in {
                "cancelled",
                "completed",
                "review",
                "published",
            }:
                continue
            stage = await db.scalar(
                select(AgricultureAnalysisStage)
                .where(
                    AgricultureAnalysisStage.run_id == run_id,
                    AgricultureAnalysisStage.stage_name == "rgb_inference",
                )
                .with_for_update()
            )
            if stage is None or (
                run.status != "waiting_inference" and stage.status != "waiting_external"
            ):
                continue
            signals = dict((stage.metrics or {}).get("completion_signals") or {})
            if job_id in signals or stage.status == "completed":
                continue
            signals[job_id] = {
                "status": status,
                "received_at": datetime.now(UTC).isoformat(),
            }
            stage.metrics = {**(stage.metrics or {}), "completion_signals": signals}
            if stage.status != "running":
                checksum, radius = _rgb_delivery(run)
                pending.append((run.id, checksum, radius))
        await db.commit()

    for run_id, checksum, radius in pending:
        agriculture_analysis_queue.enqueue_stage(
            stage="rgb_inference",
            run_id=run_id,
            input_checksum=checksum,
            cluster_radius_m=radius,
        )
    return {"matched_runs": len(run_ids), "resumed_runs": len(pending)}


async def reconcile_waiting_dependencies(limit: int = 100) -> dict[str, int]:
    """Recover lost callbacks and enforce wait timeouts without per-run polling."""
    resumable: list[tuple[str, str, float]] = []
    waiting = 0
    failed = 0
    async with Session() as db:
        run_ids = list(
            (
                await db.scalars(
                    select(AgricultureAnalysisRun.id)
                    .where(AgricultureAnalysisRun.status == "waiting_inference")
                    .order_by(AgricultureAnalysisRun.created_at.asc())
                    .limit(max(1, min(limit, 500)))
                )
            ).all()
        )
        for run_id in run_ids:
            run = await db.get(AgricultureAnalysisRun, run_id)
            flight = (
                await agriculture_repository.get_flight(db, flight_id=run.flight_id)
                if run is not None
                else None
            )
            if run is None or flight is None:
                continue
            state, _ = await agriculture_analysis_orchestration.prerequisite_state(
                db, run=run, flight=flight
            )
            if state == "completed":
                checksum, radius = _rgb_delivery(run)
                resumable.append((run.id, checksum, radius))
            elif state == "failed":
                failed += 1
                await append_analysis_event(
                    db,
                    run=run,
                    flight=flight,
                    event_type="run.failed",
                    payload={
                        "status": run.status,
                        "stage": "rgb_inference",
                        "error": run.error,
                    },
                    dedupe_key=(f"analysis:{run.id}:inference-failed:a{run.retry_count}"),
                )
                await db.commit()
            else:
                waiting += 1

    for run_id, checksum, radius in resumable:
        agriculture_analysis_queue.enqueue_stage(
            stage="rgb_inference",
            run_id=run_id,
            input_checksum=checksum,
            cluster_radius_m=radius,
        )
    return {
        "checked": len(run_ids),
        "resumed": len(resumable),
        "waiting": waiting,
        "failed": failed,
    }
