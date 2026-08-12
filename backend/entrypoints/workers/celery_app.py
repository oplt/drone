from __future__ import annotations

from celery import Celery
from celery.signals import worker_shutdown
from kombu import Queue

from backend.core.config.runtime import settings
from backend.modules.vision_models.config import vision_settings

CELERY_BROKER_URL = settings.celery_broker_url
CELERY_RESULT_BACKEND = settings.celery_result_backend
CELERY_DEFAULT_QUEUE = settings.celery_default_queue
CELERY_PHOTOGRAMMETRY_QUEUE = settings.CELERY_PHOTOGRAMMETRY_QUEUE
CELERY_WAREHOUSE_MAPPING_QUEUE = settings.celery_warehouse_mapping_queue
CELERY_VIDEO_ANALYSIS_QUEUE = settings.celery_video_analysis_queue
CELERY_VISION_TRAINING_QUEUE = vision_settings.celery_vision_training_queue
CELERY_AGRICULTURE_INFERENCE_QUEUE = settings.celery_agriculture_inference_queue
CELERY_AGRICULTURE_QUEUES = {
    "ingest": settings.celery_agriculture_ingest_queue,
    "quality": settings.celery_agriculture_quality_queue,
    "rgb_inference": settings.celery_agriculture_inference_queue,
    "segmentation": settings.celery_agriculture_segmentation_queue,
    "geospatial_aggregation": settings.celery_agriculture_geospatial_queue,
    "temporal_comparison": settings.celery_agriculture_temporal_queue,
    "sensor_fusion": settings.celery_agriculture_fusion_queue,
    "exports": settings.celery_agriculture_exports_queue,
    "dead_letter": settings.celery_agriculture_dead_letter_queue,
}
CELERY_AGRICULTURE_INFERENCE_TIME_LIMIT_SECONDS = (
    settings.celery_agriculture_inference_time_limit_seconds
)
CELERY_AGRICULTURE_INFERENCE_SOFT_TIME_LIMIT_SECONDS = (
    settings.celery_agriculture_inference_soft_time_limit_seconds
)
CELERY_WORKER_MAX_TASKS_PER_CHILD = settings.celery_worker_max_tasks_per_child
CELERY_PHOTOGRAMMETRY_TIME_LIMIT_SECONDS = settings.celery_photogrammetry_time_limit_seconds
CELERY_PHOTOGRAMMETRY_SOFT_TIME_LIMIT_SECONDS = (
    settings.celery_photogrammetry_soft_time_limit_seconds
)

celery_app = Celery(
    "drone_backend",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)


@worker_shutdown.connect
def _close_shared_cache_clients(**_kwargs: object) -> None:
    from backend.modules.platform.worker_lifecycle import close_worker_cache_clients

    close_worker_cache_clients()


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    task_default_queue=CELERY_DEFAULT_QUEUE,
    task_queues=(
        Queue(CELERY_DEFAULT_QUEUE),
        Queue(CELERY_PHOTOGRAMMETRY_QUEUE),
        Queue(CELERY_WAREHOUSE_MAPPING_QUEUE),
        Queue(CELERY_VIDEO_ANALYSIS_QUEUE),
        Queue(CELERY_VISION_TRAINING_QUEUE),
        *(Queue(name) for name in CELERY_AGRICULTURE_QUEUES.values()),
    ),
    task_routes={
        "photogrammetry.process_job": {"queue": CELERY_PHOTOGRAMMETRY_QUEUE},
        "warehouse_mapping.process_job": {"queue": CELERY_WAREHOUSE_MAPPING_QUEUE},
        "warehouse_mapping.extract_structure": {"queue": CELERY_WAREHOUSE_MAPPING_QUEUE},
        "video_analysis.process_job": {"queue": CELERY_VIDEO_ANALYSIS_QUEUE},
        "vision_models.train": {"queue": CELERY_VISION_TRAINING_QUEUE},
        "agriculture.process_run": {"queue": CELERY_AGRICULTURE_INFERENCE_QUEUE},
        "agriculture.stage.ingest": {"queue": CELERY_AGRICULTURE_QUEUES["ingest"]},
        "agriculture.stage.quality": {"queue": CELERY_AGRICULTURE_QUEUES["quality"]},
        "agriculture.stage.rgb_inference": {"queue": CELERY_AGRICULTURE_QUEUES["rgb_inference"]},
        "agriculture.stage.segmentation": {"queue": CELERY_AGRICULTURE_QUEUES["segmentation"]},
        "agriculture.stage.geospatial_aggregation": {
            "queue": CELERY_AGRICULTURE_QUEUES["geospatial_aggregation"]
        },
        "agriculture.stage.temporal_comparison": {
            "queue": CELERY_AGRICULTURE_QUEUES["temporal_comparison"]
        },
        "agriculture.stage.sensor_fusion": {"queue": CELERY_AGRICULTURE_QUEUES["sensor_fusion"]},
        "agriculture.stage.exports": {"queue": CELERY_AGRICULTURE_QUEUES["exports"]},
        "agriculture.dead_letter": {"queue": CELERY_AGRICULTURE_QUEUES["dead_letter"]},
        "agriculture.retention_cleanup": {"queue": settings.celery_agriculture_exports_queue},
        "agents.run_agent_task": {"queue": CELERY_DEFAULT_QUEUE},
        "agents.summarize_property_patrol_incident": {"queue": CELERY_DEFAULT_QUEUE},
    },
    worker_max_tasks_per_child=CELERY_WORKER_MAX_TASKS_PER_CHILD,
    task_annotations={
        "agriculture.process_run": {"rate_limit": "4/m"},
        "agriculture.stage.ingest": {"rate_limit": "120/m"},
        "agriculture.stage.quality": {"rate_limit": "12/m"},
        "agriculture.stage.rgb_inference": {"rate_limit": "4/m"},
        "agriculture.stage.segmentation": {"rate_limit": "4/m"},
        "agriculture.stage.geospatial_aggregation": {"rate_limit": "12/m"},
        "agriculture.stage.temporal_comparison": {"rate_limit": "12/m"},
        "agriculture.stage.sensor_fusion": {"rate_limit": "12/m"},
        "agriculture.stage.exports": {"rate_limit": "20/m"},
        "agriculture.retention_cleanup": {"rate_limit": "1/h"},
    },
    task_time_limit=CELERY_PHOTOGRAMMETRY_TIME_LIMIT_SECONDS,
    task_soft_time_limit=CELERY_PHOTOGRAMMETRY_SOFT_TIME_LIMIT_SECONDS,
)

celery_app.autodiscover_tasks(["backend.entrypoints.workers"])

celery_app.conf.beat_schedule = {
    "check-due-templates": {
        "task": "backend.tasks.scheduling_tasks.check_due_templates",
        "schedule": 60.0,  # every 60 seconds
    },
    "publish-pending-outbox": {
        "task": "backend.tasks.outbox_tasks.publish_pending_outbox",
        "schedule": 5.0,
    },
    "deliver-pending-webhooks": {
        "task": "backend.tasks.webhook_tasks.deliver_pending_webhooks",
        "schedule": 5.0,
    },
    "monitor-irrigation-jobs": {
        "task": "irrigation.monitor_tick",
        "schedule": 30.0,
    },
    "cleanup-agriculture-retention": {
        "task": "agriculture.retention_cleanup",
        "schedule": 3600.0,
    },
}
celery_app.conf.timezone = "UTC"

from backend.observability.celery_instrumentation import instrument_celery  # noqa: E402

instrument_celery(celery_app)

# Celery workers are launched with ``-A backend.entrypoints.workers.celery_app``.
# Import task modules here so direct submodule loading still registers every
# named task; relying on package ``__init__`` is not enough for this entrypoint.
from backend.entrypoints.workers import (  # noqa: E402, F401
    agents_tasks,
    agriculture_tasks,
    deliverable_tasks,
    export_tasks,
    irrigation_tasks,
    outbox_tasks,
    photogrammetry_tasks,
    scheduling_tasks,
    video_analysis_tasks,
    vision_models_tasks,
    warehouse_mapping_tasks,
    webhook_tasks,
)
