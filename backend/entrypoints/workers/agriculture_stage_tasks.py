"""Celery adapters for independently scalable agriculture stages."""

from __future__ import annotations

from time import time

from celery import Task

from backend.core.config.runtime import settings
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.agriculture.dependency_events import (
    reconcile_waiting_dependencies,
    resume_runs_for_video_job,
)
from backend.modules.agriculture.stage_checkpoints import checkpoint_stage
from backend.modules.agriculture.stage_executor import execute_stage, queue_for_stage
from backend.modules.agriculture.stage_failures import record_stage_failure
from backend.observability import prometheus_metrics
from backend.observability.instruments import observed_span

_worker_loop = WorkerLoopState()


class AgricultureStageTask(Task):
    """Uniform bounded retry and dead-letter policy for isolated stages."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = settings.agriculture_stage_max_retries

    @staticmethod
    def _stage_name(task_name: str | None) -> str | None:
        prefix = "agriculture.stage."
        if task_name and task_name.startswith(prefix):
            return task_name[len(prefix) :]
        return None

    def _record(self, run_id: str, *, status: str, error: str, task_id: str) -> None:
        stage_name = self._stage_name(self.name)
        if stage_name is None:
            return
        terminal = status == "dead_letter"
        try:
            _worker_loop.run(
                record_stage_failure(
                    run_id,
                    stage_name,
                    status=status,
                    error=error,
                    dead_letter=terminal,
                    task_id=task_id,
                    retryable=not terminal,
                )
            )
        except Exception:
            # Failure reporting must never mask the original Celery exception.
            pass

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        run_id = kwargs.get("run_id") or (args[0] if args else None)
        if run_id:
            self._record(str(run_id), status="retrying", error=str(exc), task_id=task_id)
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        run_id = kwargs.get("run_id") or (args[0] if args else None)
        terminal = self.request.retries >= self.max_retries
        if run_id:
            self._record(
                str(run_id),
                status="dead_letter" if terminal else "failed",
                error=str(exc),
                task_id=task_id,
            )
        if run_id and terminal:
            self.app.send_task(
                "agriculture.dead_letter",
                kwargs={"run_id": run_id, "error": str(exc), "task_name": self.name},
                queue=settings.celery_agriculture_dead_letter_queue,
            )
        super().on_failure(exc, task_id, args, kwargs, einfo)


def _run_stage(
    task,
    run_id: str,
    stage_name: str,
    input_checksum: str,
    *,
    cluster_radius_m: float = 8.0,
    export_id: str | None = None,
    agriculture_queued_at: float | None = None,
) -> dict[str, str]:
    queue_name = queue_for_stage(stage_name)
    queue_age_seconds = (
        max(0.0, time() - float(agriculture_queued_at))
        if agriculture_queued_at is not None
        else 0.0
    )
    prometheus_metrics.agriculture_queue_age_seconds.labels(queue=queue_name).observe(
        queue_age_seconds
    )
    with observed_span("agriculture.stage", run_id=run_id, stage=stage_name):
        return _worker_loop.run(
            execute_stage(
                run_id,
                stage_name,
                input_checksum,
                task_id=str(task.request.id or "inline"),
                queue_name=queue_name,
                cluster_radius_m=cluster_radius_m,
                export_id=export_id,
                queue_age_seconds=queue_age_seconds,
            )
        )


def _stage_task(name: str, *, time_limit: int, soft_time_limit: int):
    return celery_app.task(
        bind=True,
        base=AgricultureStageTask,
        name=f"agriculture.stage.{name}",
        time_limit=time_limit,
        soft_time_limit=soft_time_limit,
    )


def _run_checkpoint(run_id: str, stage_name: str, input_checksum: str) -> dict[str, str]:
    with observed_span("agriculture.stage", run_id=run_id, stage=stage_name):
        return _worker_loop.run(checkpoint_stage(run_id, stage_name, input_checksum))


@celery_app.task(
    base=AgricultureStageTask,
    name="agriculture.stage.ingest",
    time_limit=300,
    soft_time_limit=240,
)
def agriculture_ingest_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "ingest", input_checksum)


@celery_app.task(
    base=AgricultureStageTask,
    name="agriculture.stage.quality",
    time_limit=900,
    soft_time_limit=840,
)
def agriculture_quality_stage(run_id: str, input_checksum: str) -> dict[str, str]:
    return _run_checkpoint(run_id, "quality", input_checksum)


@_stage_task("rgb_inference", time_limit=1800, soft_time_limit=1500)
def agriculture_rgb_inference_stage(
    self, run_id, input_checksum, cluster_radius_m=8.0, agriculture_queued_at=None
):
    return _run_stage(
        self,
        run_id,
        "rgb_inference",
        input_checksum,
        cluster_radius_m=cluster_radius_m,
        agriculture_queued_at=agriculture_queued_at,
    )


@_stage_task("geospatial_aggregation", time_limit=1200, soft_time_limit=1080)
def agriculture_geospatial_stage(
    self, run_id, input_checksum, cluster_radius_m=8.0, agriculture_queued_at=None
):
    return _run_stage(
        self,
        run_id,
        "geospatial_aggregation",
        input_checksum,
        cluster_radius_m=cluster_radius_m,
        agriculture_queued_at=agriculture_queued_at,
    )


@_stage_task("segmentation", time_limit=1800, soft_time_limit=1500)
def agriculture_segmentation_stage(
    self, run_id, input_checksum, cluster_radius_m=8.0, agriculture_queued_at=None
):
    return _run_stage(
        self,
        run_id,
        "segmentation",
        input_checksum,
        cluster_radius_m=cluster_radius_m,
        agriculture_queued_at=agriculture_queued_at,
    )


@_stage_task("temporal_comparison", time_limit=900, soft_time_limit=840)
def agriculture_temporal_stage(
    self, run_id, input_checksum, cluster_radius_m=8.0, agriculture_queued_at=None
):
    return _run_stage(
        self,
        run_id,
        "temporal_comparison",
        input_checksum,
        cluster_radius_m=cluster_radius_m,
        agriculture_queued_at=agriculture_queued_at,
    )


@_stage_task("sensor_fusion", time_limit=900, soft_time_limit=840)
def agriculture_fusion_stage(
    self, run_id, input_checksum, cluster_radius_m=8.0, agriculture_queued_at=None
):
    return _run_stage(
        self,
        run_id,
        "sensor_fusion",
        input_checksum,
        cluster_radius_m=cluster_radius_m,
        agriculture_queued_at=agriculture_queued_at,
    )


@_stage_task("exports", time_limit=900, soft_time_limit=840)
def agriculture_export_stage(
    self, run_id, input_checksum, cluster_radius_m=8.0, export_id=None, agriculture_queued_at=None
):
    return _run_stage(
        self,
        run_id,
        "exports",
        input_checksum,
        cluster_radius_m=cluster_radius_m,
        export_id=export_id,
        agriculture_queued_at=agriculture_queued_at,
    )


@celery_app.task(name="agriculture.video_inference_completed", time_limit=120, soft_time_limit=90)
def agriculture_video_inference_completed(job_id: str, status: str) -> dict[str, int]:
    return _worker_loop.run(resume_runs_for_video_job(job_id, status))


@celery_app.task(
    name="agriculture.reconcile_waiting_dependencies", time_limit=300, soft_time_limit=240
)
def agriculture_reconcile_waiting_dependencies() -> dict[str, int]:
    return _worker_loop.run(reconcile_waiting_dependencies())
