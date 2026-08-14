from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import monotonic, time

from sqlalchemy import delete, select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import (
    CELERY_AGRICULTURE_INFERENCE_QUEUE,
    CELERY_AGRICULTURE_INFERENCE_SOFT_TIME_LIMIT_SECONDS,
    CELERY_AGRICULTURE_INFERENCE_TIME_LIMIT_SECONDS,
    celery_app,
)
from backend.modules.agriculture.lifecycle import append_analysis_event
from backend.modules.agriculture.models import (
    AgricultureAnalysisRun,
    AgricultureAnalysisStage,
    AgricultureMediaManifest,
    AgricultureUploadSession,
)
from backend.modules.agriculture.p5_models import AgricultureExportJob
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.stage_operations import stage_input_checksum
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.workflow_events.models import WorkflowEvent
from backend.observability import prometheus_metrics
from backend.observability.instruments import observed_span

_worker_loop = WorkerLoopState()


async def _process(
    run_id: str,
    *,
    force: bool = False,
    cluster_radius_m: float = 8.0,
    queue_age_seconds: float = 0.0,
) -> dict[str, str]:
    """Compatibility orchestrator that enqueues the first real stage."""
    async with Session() as db:
        run = await db.scalar(
            select(AgricultureAnalysisRun)
            .where(AgricultureAnalysisRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ValueError(f"Agriculture analysis run not found: {run_id}")
        if run.status in {"cancelled", "review", "published", "completed"} and not force:
            return {"run_id": run_id, "status": run.status}
        owner_key = f"agri-orchestrator:{run.id}:a{run.retry_count}"
        pipeline_stage = await db.scalar(
            select(AgricultureAnalysisStage)
            .where(
                AgricultureAnalysisStage.run_id == run.id,
                AgricultureAnalysisStage.stage_name == "pipeline_execution",
            )
            .with_for_update()
        )
        if pipeline_stage is None:
            pipeline_stage = AgricultureAnalysisStage(
                run_id=run.id,
                stage_name="pipeline_execution",
            )
            db.add(pipeline_stage)
        elif (
            pipeline_stage.status == "completed"
            and pipeline_stage.execution_key == owner_key
            and pipeline_stage.task_id
        ):
            return {"run_id": run_id, "status": run.status, "stage": "rgb_inference"}

        input_checksum = stage_input_checksum(
            run,
            "rgb_inference",
            extra={"cluster_radius_m": cluster_radius_m},
        )
        pipeline_stage.status = "running"
        pipeline_stage.execution_key = owner_key
        pipeline_stage.input_checksum = input_checksum
        pipeline_stage.attempt += 1
        pipeline_stage.progress = 0.0
        pipeline_stage.error = None
        pipeline_stage.started_at = datetime.now(UTC)
        pipeline_stage.finished_at = None
        run.status = "orchestrating"
        run.counters = {
            **(run.counters or {}),
            "queue_age_seconds": max(0.0, queue_age_seconds),
            "worker_started_at": datetime.now(UTC).isoformat(),
            "pipeline_execution_key": owner_key,
            "cluster_radius_m": cluster_radius_m,
        }
        flight = await agriculture_repository.get_flight(db, flight_id=run.flight_id)
        if flight is None:
            raise ValueError(f"Agriculture flight not found for run: {run_id}")
        await append_analysis_event(
            db,
            run=run,
            flight=flight,
            event_type="run.started",
            payload={"status": run.status, "stage": "rgb_inference"},
            dedupe_key=f"analysis:{run.id}:started:a{run.retry_count}",
        )
        pipeline_stage.status = "completed"
        pipeline_stage.progress = 100.0
        pipeline_stage.output_checksum = input_checksum
        pipeline_stage.finished_at = datetime.now(UTC)
        pipeline_stage.metrics = {
            "coordination_only": True,
            "first_stage": "rgb_inference",
            "queue_age_seconds": max(0.0, queue_age_seconds),
        }
        await db.commit()

        task = celery_app.send_task(
            "agriculture.stage.rgb_inference",
            kwargs={
                "run_id": run.id,
                "input_checksum": input_checksum,
                "cluster_radius_m": cluster_radius_m,
                "agriculture_queued_at": time(),
            },
            queue=settings.celery_agriculture_inference_queue,
        )
        pipeline_stage.task_id = str(task.id)
        await db.commit()
        return {"run_id": run_id, "status": run.status, "stage": "rgb_inference"}


async def _dead_letter(run_id: str, *, error: str, task_name: str) -> dict[str, str]:
    async with Session() as db:
        run = await db.scalar(
            select(AgricultureAnalysisRun)
            .where(AgricultureAnalysisRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            return {"run_id": run_id, "status": "missing"}
        run.status = "failed"
        run.error = error[:4000]
        stage_name = task_name.removeprefix("agriculture.stage.")
        run.audit_json = {
            **(run.audit_json or {}),
            "dead_letter": {
                "task": task_name,
                "stage": stage_name,
                "error": error[:1000],
                "failed_at": datetime.now(UTC).isoformat(),
                "replayable": True,
            },
        }
        stage = await db.scalar(
            select(AgricultureAnalysisStage)
            .where(
                AgricultureAnalysisStage.run_id == run_id,
                AgricultureAnalysisStage.stage_name == stage_name,
            )
            .with_for_update()
        )
        if stage is not None:
            stage.status = "dead_letter"
            stage.error = error[:4000]
            stage.retryable = True
            stage.dead_letter = True
            stage.dead_letter_at = datetime.now(UTC)
        flight = await agriculture_repository.get_flight(db, flight_id=run.flight_id)
        if flight is not None:
            await append_analysis_event(
                db,
                run=run,
                flight=flight,
                event_type="run.failed",
                payload={
                    "status": run.status,
                    "stage": stage_name,
                    "dead_letter": True,
                    "retryable": True,
                    "error": error[:1000],
                },
                dedupe_key=(
                    f"analysis:{run.id}:{stage_name}:dead-letter:"
                    f"a{stage.attempt if stage else run.retry_count}"
                ),
            )
        await db.commit()
        return {"run_id": run_id, "status": "dead_letter"}


@celery_app.task(name="agriculture.dead_letter", time_limit=120, soft_time_limit=90)
def agriculture_dead_letter(run_id: str, error: str, task_name: str) -> dict[str, str]:
    prometheus_metrics.agriculture_dead_letters_total.labels(task=task_name).inc()
    return _worker_loop.run(_dead_letter(run_id, error=error, task_name=task_name))


@celery_app.task(
    bind=True,
    max_retries=2,
    name="agriculture.process_run",
    time_limit=CELERY_AGRICULTURE_INFERENCE_TIME_LIMIT_SECONDS,
    soft_time_limit=CELERY_AGRICULTURE_INFERENCE_SOFT_TIME_LIMIT_SECONDS,
)
def process_agriculture_run(
    self,
    run_id: str,
    force: bool = False,
    cluster_radius_m: float = 8.0,
    agriculture_queued_at: float | None = None,
) -> dict[str, str]:
    started = monotonic()
    queue_name = CELERY_AGRICULTURE_INFERENCE_QUEUE
    queued_at = (
        getattr(self.request, "headers", {}).get("agriculture_queued_at")
        or agriculture_queued_at
    )
    queue_age_seconds = 0.0
    if queued_at:
        try:
            queue_age_seconds = max(0.0, time() - float(queued_at))
            prometheus_metrics.agriculture_queue_age_seconds.labels(
                queue=queue_name
            ).observe(queue_age_seconds)
        except (TypeError, ValueError):
            pass
    prometheus_metrics.agriculture_queue_depth.labels(queue=queue_name).set(0)
    prometheus_metrics.agriculture_runs_started_total.labels(queue=queue_name).inc()
    try:
        with observed_span(
            "agriculture.process_run", run_id=run_id, queue=queue_name, force=force
        ):
            result = _worker_loop.run(
                _process(
                    run_id,
                    force=force,
                    cluster_radius_m=cluster_radius_m,
                    queue_age_seconds=queue_age_seconds,
                )
            )
        prometheus_metrics.agriculture_runs_completed_total.labels(
            queue=queue_name, status=result["status"]
        ).inc()
        prometheus_metrics.agriculture_run_duration_seconds.labels(
            queue=queue_name
        ).observe(monotonic() - started)
        return result
    except Exception as exc:
        prometheus_metrics.agriculture_runs_failed_total.labels(
            queue=queue_name, error_type=type(exc).__name__
        ).inc()
        prometheus_metrics.agriculture_run_duration_seconds.labels(
            queue=queue_name
        ).observe(monotonic() - started)
        if self.request.retries >= self.max_retries:
            agriculture_dead_letter.apply_async(
                kwargs={"run_id": run_id, "error": str(exc), "task_name": self.name}
            )
            raise
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(
                attempt=self.request.retries, max_seconds=300
            ),
        ) from exc


async def _cleanup_retention() -> dict[str, int]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=max(1, settings.agriculture_media_retention_days))
    deleted = 0
    async with Session() as db:
        rows = list(
            (
                await db.scalars(
                    select(AgricultureMediaManifest)
                    .where(
                        AgricultureMediaManifest.retention_status == "active",
                        (
                            AgricultureMediaManifest.retention_expires_at.is_not(None)
                            & (AgricultureMediaManifest.retention_expires_at <= now)
                        )
                        | (
                            AgricultureMediaManifest.retention_expires_at.is_(None)
                            & (AgricultureMediaManifest.created_at < cutoff)
                        ),
                    )
                    .limit(500)
                )
            ).all()
        )
        for row in rows:
            try:
                agriculture_storage.delete(row.storage_key)
            except (FileNotFoundError, ValueError):
                pass
            row.retention_status = "expired"
            deleted += 1
        upload_rows = list(
            (
                await db.scalars(
                    select(AgricultureUploadSession)
                    .where(
                        AgricultureUploadSession.status == "uploading",
                        AgricultureUploadSession.expires_at < now,
                    )
                    .limit(500)
                )
            ).all()
        )
        for row in upload_rows:
            try:
                agriculture_storage.delete(row.temporary_key)
            except (FileNotFoundError, ValueError):
                pass
            row.status = "expired"
        export_rows = list(
            (
                await db.scalars(
                    select(AgricultureExportJob)
                    .where(
                        AgricultureExportJob.status == "ready",
                        AgricultureExportJob.expires_at < now,
                    )
                    .limit(500)
                )
            ).all()
        )
        for row in export_rows:
            if row.storage_key:
                try:
                    agriculture_storage.delete(row.storage_key)
                except (FileNotFoundError, ValueError):
                    pass
            row.status = "expired"
        event_cutoff = now - timedelta(
            days=max(1, settings.workflow_event_retention_days)
        )
        workflow_events_expired = int(
            (
                await db.execute(
                    delete(WorkflowEvent)
                    .where(WorkflowEvent.created_at < event_cutoff)
                    .execution_options(synchronize_session=False)
                )
            ).rowcount
            or 0
        )
        await db.commit()
    return {
        "expired": deleted,
        "uploads_expired": len(upload_rows),
        "exports_expired": len(export_rows),
        "workflow_events_expired": workflow_events_expired,
    }


@celery_app.task(
    bind=True,
    max_retries=2,
    name="agriculture.retention_cleanup",
    time_limit=300,
    soft_time_limit=240,
)
def cleanup_agriculture_retention(self) -> dict[str, int]:
    try:
        return _worker_loop.run(_cleanup_retention())
    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(
                attempt=self.request.retries, max_seconds=300
            ),
        ) from exc
