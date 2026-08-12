from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from time import monotonic, time

from celery import Task

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.celery_app import CELERY_AGRICULTURE_INFERENCE_QUEUE, CELERY_AGRICULTURE_INFERENCE_SOFT_TIME_LIMIT_SECONDS, CELERY_AGRICULTURE_INFERENCE_TIME_LIMIT_SECONDS, celery_app
from backend.core.database.session import Session
from backend.observability import prometheus_metrics
from backend.observability.instruments import observed_span
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.service import agriculture_service
from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureAnalysisStage
from sqlalchemy import select
from backend.modules.agriculture.models import AgricultureMediaManifest, AgricultureUploadSession
from backend.modules.agriculture.p5_models import AgricultureExportJob
from backend.modules.agriculture.storage import agriculture_storage
from backend.core.config.runtime import settings


class AgricultureStageTask(Task):
    """Uniform bounded retry and dead-letter policy for isolated stage workers."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = settings.agriculture_stage_max_retries

    @staticmethod
    def _stage_name(task_name: str | None) -> str | None:
        prefix = "agriculture.stage."
        return task_name[len(prefix):] if task_name and task_name.startswith(prefix) else None

    @staticmethod
    def _record_stage(run_id: str, task_name: str | None, *, status: str, error: str | None = None, dead_letter: bool = False, task_id: str | None = None, retryable: bool = True) -> None:
        stage_name = AgricultureStageTask._stage_name(task_name)
        if not stage_name:
            return

        async def _write() -> None:
            async with Session() as db:
                stage = await db.scalar(select(AgricultureAnalysisStage).where(AgricultureAnalysisStage.run_id == run_id, AgricultureAnalysisStage.stage_name == stage_name).with_for_update())
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
                await db.commit()

        try:
            asyncio.run(_write())
        except Exception:
            # Worker failure reporting must never mask the original Celery error.
            pass

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        run_id = kwargs.get("run_id") or (args[0] if args else None)
        if run_id:
            self._record_stage(str(run_id), self.name, status="retrying", error=str(exc), task_id=task_id, retryable=True)
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        run_id = kwargs.get("run_id") or (args[0] if args else None)
        if run_id:
            terminal = self.request.retries >= self.max_retries
            self._record_stage(str(run_id), self.name, status="dead_letter" if terminal else "failed", error=str(exc), dead_letter=terminal, task_id=task_id, retryable=not terminal)
        if run_id and self.request.retries >= self.max_retries:
            self.app.send_task(
                "agriculture.dead_letter",
                kwargs={"run_id": run_id, "error": str(exc), "task_name": self.name},
                queue=settings.celery_agriculture_dead_letter_queue,
            )
        super().on_failure(exc, task_id, args, kwargs, einfo)


async def _process(
    run_id: str,
    *,
    force: bool = False,
    cluster_radius_m: float = 8.0,
    queue_age_seconds: float = 0.0,
    execution_key: str | None = None,
) -> dict[str, str]:
    async with Session() as db:
        run = await db.scalar(select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.id == run_id).with_for_update())
        if run is None:
            raise ValueError(f"Agriculture analysis run not found: {run_id}")
        if run.status in {"cancelled", "review", "published", "completed"} and not force:
            return {"run_id": run_id, "status": run.status}
        owner_key = (
            f"agri-pipeline:{run.id}:a{run.retry_count}:"
            f"{execution_key or 'inline'}"
        )
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
            pipeline_stage.status == "running"
            and pipeline_stage.execution_key != owner_key
            and run.status in {"orchestrating", "running"}
            and not force
        ):
            return {"run_id": run_id, "status": run.status}
        pipeline_stage.status = "running"
        pipeline_stage.execution_key = owner_key
        pipeline_stage.input_checksum = hashlib.sha256(
            f"{run.input_checksum}:{run.retry_count}:{cluster_radius_m}".encode()
        ).hexdigest()
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
        }
        await db.commit()
        flight = await agriculture_repository.get_flight(db, flight_id=run.flight_id)
        if flight is None:
            raise ValueError(f"Agriculture flight not found for run: {run_id}")
        try:
            with observed_span(
                "agriculture.analysis_pipeline",
                run_id=run.id,
                flight_id=flight.id,
                field_id=flight.field_id,
                mission_id=flight.mission_id,
            ):
                await agriculture_service.process_analysis_run(db, run=run, flight=flight, force=force, cluster_radius_m=cluster_radius_m)
        except Exception as exc:
            pipeline_stage = await db.scalar(
                select(AgricultureAnalysisStage)
                .where(
                    AgricultureAnalysisStage.run_id == run.id,
                    AgricultureAnalysisStage.stage_name == "pipeline_execution",
                    AgricultureAnalysisStage.execution_key == owner_key,
                )
                .with_for_update()
            )
            if pipeline_stage is not None:
                pipeline_stage.status = "failed"
                pipeline_stage.error = str(exc)[:4000]
                pipeline_stage.finished_at = datetime.now(UTC)
                await db.commit()
            raise
        pipeline_stage = await db.scalar(
            select(AgricultureAnalysisStage)
            .where(
                AgricultureAnalysisStage.run_id == run.id,
                AgricultureAnalysisStage.stage_name == "pipeline_execution",
                AgricultureAnalysisStage.execution_key == owner_key,
            )
            .with_for_update()
        )
        if pipeline_stage is not None:
            if run.status == "waiting_inference":
                pipeline_stage.status = "queued"
                pipeline_stage.execution_key = None
                pipeline_stage.progress = run.progress
            else:
                pipeline_stage.status = (
                    "failed" if run.status == "failed" else "completed"
                )
                pipeline_stage.progress = 100.0
                pipeline_stage.finished_at = datetime.now(UTC)
            await db.commit()
        return {"run_id": run_id, "status": run.status}


async def _checkpoint_stage(run_id: str, stage_name: str, input_checksum: str) -> dict[str, str]:
    """Idempotent worker boundary used by independently scaled stage queues."""
    async with Session() as db:
        run = await db.scalar(select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.id == run_id).with_for_update())
        if run is None:
            raise ValueError(f"Agriculture analysis run not found: {run_id}")
        if run.status == "cancelled":
            return {"run_id": run_id, "stage": stage_name, "status": "cancelled"}
        stage = await db.scalar(select(AgricultureAnalysisStage).where(
            AgricultureAnalysisStage.run_id == run_id,
            AgricultureAnalysisStage.stage_name == stage_name,
        ).with_for_update())
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


def _run_checkpoint(run_id: str, stage_name: str, input_checksum: str) -> dict[str, str]:
    with observed_span("agriculture.stage", run_id=run_id, stage=stage_name):
        return asyncio.run(_checkpoint_stage(run_id, stage_name, input_checksum))


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.ingest", time_limit=300, soft_time_limit=240)
def agriculture_ingest_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "ingest", input_checksum)


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.quality", time_limit=900, soft_time_limit=840)
def agriculture_quality_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "quality", input_checksum)


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.rgb_inference", time_limit=1800, soft_time_limit=1500)
def agriculture_rgb_inference_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "rgb_inference", input_checksum)


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.segmentation", time_limit=1800, soft_time_limit=1500)
def agriculture_segmentation_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "segmentation", input_checksum)


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.geospatial_aggregation", time_limit=1200, soft_time_limit=1080)
def agriculture_geospatial_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "geospatial_aggregation", input_checksum)


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.temporal_comparison", time_limit=900, soft_time_limit=840)
def agriculture_temporal_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "temporal_comparison", input_checksum)


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.sensor_fusion", time_limit=900, soft_time_limit=840)
def agriculture_fusion_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "sensor_fusion", input_checksum)


@celery_app.task(base=AgricultureStageTask, name="agriculture.stage.exports", time_limit=900, soft_time_limit=840)
def agriculture_export_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "exports", input_checksum)


async def _dead_letter(run_id: str, *, error: str, task_name: str) -> dict[str, str]:
    async with Session() as db:
        run = await db.scalar(select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.id == run_id).with_for_update())
        if run is None:
            return {"run_id": run_id, "status": "missing"}
        run.status = "failed"
        run.error = error[:4000]
        run.audit_json = {
            **(run.audit_json or {}),
            "dead_letter": {
                "task": task_name,
                "stage": task_name.removeprefix("agriculture.stage."),
                "error": error[:1000],
                "failed_at": datetime.now(UTC).isoformat(),
                "replayable": True,
            },
        }
        stage_name = task_name.removeprefix("agriculture.stage.")
        stage = await db.scalar(select(AgricultureAnalysisStage).where(AgricultureAnalysisStage.run_id == run_id, AgricultureAnalysisStage.stage_name == stage_name).with_for_update())
        if stage is not None:
            stage.status = "dead_letter"
            stage.error = error[:4000]
            stage.retryable = True
            stage.dead_letter = True
            stage.dead_letter_at = datetime.now(UTC)
        await db.commit()
        return {"run_id": run_id, "status": "dead_letter"}


@celery_app.task(name="agriculture.dead_letter")
def agriculture_dead_letter(run_id: str, error: str, task_name: str) -> dict[str, str]:
    prometheus_metrics.agriculture_dead_letters_total.labels(task=task_name).inc()
    return asyncio.run(_dead_letter(run_id, error=error, task_name=task_name))


@celery_app.task(bind=True, max_retries=2, name="agriculture.process_run", time_limit=CELERY_AGRICULTURE_INFERENCE_TIME_LIMIT_SECONDS, soft_time_limit=CELERY_AGRICULTURE_INFERENCE_SOFT_TIME_LIMIT_SECONDS)
def process_agriculture_run(self, run_id: str, force: bool = False, cluster_radius_m: float = 8.0, agriculture_queued_at: float | None = None) -> dict[str, str]:
    started = monotonic()
    queue_name = CELERY_AGRICULTURE_INFERENCE_QUEUE
    queued_at = getattr(self.request, "headers", {}).get("agriculture_queued_at") or agriculture_queued_at
    queue_age_seconds = 0.0
    if queued_at:
        try:
            queue_age_seconds = max(0.0, time() - float(queued_at))
            prometheus_metrics.agriculture_queue_age_seconds.labels(queue=queue_name).observe(queue_age_seconds)
        except (TypeError, ValueError):
            pass
    prometheus_metrics.agriculture_queue_depth.labels(queue=queue_name).set(0)
    prometheus_metrics.agriculture_runs_started_total.labels(queue=queue_name).inc()
    try:
        with observed_span("agriculture.process_run", run_id=run_id, queue=queue_name, force=force):
            result = asyncio.run(
                _process(
                    run_id,
                    force=force,
                    cluster_radius_m=cluster_radius_m,
                    queue_age_seconds=queue_age_seconds,
                    execution_key=str(self.request.id or "inline"),
                )
            )
        if result["status"] == "waiting_inference":
            self.apply_async(
                kwargs={
                    "run_id": run_id,
                    "force": False,
                    "cluster_radius_m": cluster_radius_m,
                    "agriculture_queued_at": time(),
                },
                countdown=settings.agriculture_inference_poll_seconds,
                queue=queue_name,
            )
        prometheus_metrics.agriculture_runs_completed_total.labels(queue=queue_name, status=result["status"]).inc()
        prometheus_metrics.agriculture_run_duration_seconds.labels(queue=queue_name).observe(monotonic() - started)
        return result
    except Exception as exc:
        prometheus_metrics.agriculture_runs_failed_total.labels(queue=queue_name, error_type=type(exc).__name__).inc()
        prometheus_metrics.agriculture_run_duration_seconds.labels(queue=queue_name).observe(monotonic() - started)
        if self.request.retries >= self.max_retries:
            agriculture_dead_letter.apply_async(kwargs={"run_id": run_id, "error": str(exc), "task_name": self.name})
            raise
        raise self.retry(exc=exc, countdown=retry_delay_seconds(attempt=self.request.retries, max_seconds=300)) from exc


@celery_app.task(bind=True, max_retries=2, name="agriculture.retention_cleanup", time_limit=300, soft_time_limit=240)
def cleanup_agriculture_retention(self) -> dict[str, int]:
    async def _cleanup() -> dict[str, int]:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=max(1, settings.agriculture_media_retention_days))
        deleted = 0
        async with Session() as db:
            rows = list((await db.scalars(select(AgricultureMediaManifest).where(
                AgricultureMediaManifest.retention_status == "active",
                ((AgricultureMediaManifest.retention_expires_at.is_not(None) & (AgricultureMediaManifest.retention_expires_at <= now)) |
                 (AgricultureMediaManifest.retention_expires_at.is_(None) & (AgricultureMediaManifest.created_at < cutoff))),
            ).limit(500))).all())
            for row in rows:
                try:
                    agriculture_storage.delete(row.storage_key)
                except (FileNotFoundError, ValueError):
                    pass
                row.retention_status = "expired"
                deleted += 1
            upload_rows = list((await db.scalars(select(AgricultureUploadSession).where(AgricultureUploadSession.status == "uploading", AgricultureUploadSession.expires_at < datetime.now(UTC)).limit(500))).all())
            for row in upload_rows:
                try:
                    agriculture_storage.delete(row.temporary_key)
                except (FileNotFoundError, ValueError):
                    pass
                row.status = "expired"
            export_rows = list((await db.scalars(select(AgricultureExportJob).where(AgricultureExportJob.status == "ready", AgricultureExportJob.expires_at < datetime.now(UTC)).limit(500))).all())
            for row in export_rows:
                if row.storage_key:
                    try:
                        agriculture_storage.delete(row.storage_key)
                    except (FileNotFoundError, ValueError):
                        pass
                row.status = "expired"
            await db.commit()
        return {"expired": deleted, "uploads_expired": len(upload_rows), "exports_expired": len(export_rows)}

    try:
        return asyncio.run(_cleanup())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=retry_delay_seconds(attempt=self.request.retries, max_seconds=300)) from exc
