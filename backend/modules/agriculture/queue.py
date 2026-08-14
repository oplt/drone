from __future__ import annotations

import logging
import time

from backend.core.config.runtime import settings
from backend.infrastructure.jobs import enqueue_task

logger = logging.getLogger(__name__)


class AgricultureAnalysisQueueError(RuntimeError):
    pass


class AgricultureAnalysisQueue:
    STAGE_TASKS = {
        "rgb_inference": ("agriculture.stage.rgb_inference", "celery_agriculture_inference_queue"),
        "segmentation": ("agriculture.stage.segmentation", "celery_agriculture_segmentation_queue"),
        "geospatial_aggregation": ("agriculture.stage.geospatial_aggregation", "celery_agriculture_geospatial_queue"),
        "temporal_comparison": ("agriculture.stage.temporal_comparison", "celery_agriculture_temporal_queue"),
        "sensor_fusion": ("agriculture.stage.sensor_fusion", "celery_agriculture_fusion_queue"),
        "exports": ("agriculture.stage.exports", "celery_agriculture_exports_queue"),
    }

    def enqueue_stage(
        self,
        *,
        stage: str,
        run_id: str,
        input_checksum: str,
        cluster_radius_m: float = 8.0,
        export_id: str | None = None,
    ) -> str:
        try:
            task_name, queue_setting = self.STAGE_TASKS[stage]
        except KeyError as exc:
            raise AgricultureAnalysisQueueError(f"Unsupported agriculture stage: {stage}") from exc
        kwargs = {
            "run_id": run_id,
            "input_checksum": input_checksum,
            "cluster_radius_m": cluster_radius_m,
        }
        if export_id is not None:
            kwargs["export_id"] = export_id
        try:
            return enqueue_task(
                task_name,
                queue=getattr(settings, queue_setting),
                agriculture_queued_at=time.time(),
                **kwargs,
            )
        except Exception as exc:
            raise AgricultureAnalysisQueueError(
                f"Failed to enqueue agriculture stage '{stage}'."
            ) from exc
    def enqueue(self, *, run_id: str, force: bool = False, cluster_radius_m: float = 8.0) -> str:
        try:
            task_id = enqueue_task("agriculture.process_run", queue=settings.celery_agriculture_inference_queue, agriculture_queued_at=time.time(), run_id=run_id, force=force, cluster_radius_m=cluster_radius_m)
        except Exception as exc:
            raise AgricultureAnalysisQueueError("Failed to enqueue agriculture analysis.") from exc
        logger.info("Enqueued agriculture analysis run run_id=%s task_id=%s", run_id, task_id)
        return task_id

    def replay(self, *, run_id: str, cluster_radius_m: float = 8.0) -> str:
        return self.enqueue(run_id=run_id, force=True, cluster_radius_m=cluster_radius_m)


agriculture_analysis_queue = AgricultureAnalysisQueue()
