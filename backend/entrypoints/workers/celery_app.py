from __future__ import annotations

import os

from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_DEFAULT_QUEUE = os.getenv("CELERY_DEFAULT_QUEUE", "default")
CELERY_PHOTOGRAMMETRY_QUEUE = os.getenv("CELERY_PHOTOGRAMMETRY_QUEUE", "photogrammetry")
CELERY_WAREHOUSE_MAPPING_QUEUE = os.getenv("CELERY_WAREHOUSE_MAPPING_QUEUE", "warehouse-mapping")
CELERY_VIDEO_ANALYSIS_QUEUE = os.getenv("CELERY_VIDEO_ANALYSIS_QUEUE", "video-analysis")
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "5"))
CELERY_PHOTOGRAMMETRY_TIME_LIMIT_SECONDS = int(
    os.getenv("CELERY_PHOTOGRAMMETRY_TIME_LIMIT_SECONDS", str(6 * 60 * 60))
)
CELERY_PHOTOGRAMMETRY_SOFT_TIME_LIMIT_SECONDS = int(
    os.getenv("CELERY_PHOTOGRAMMETRY_SOFT_TIME_LIMIT_SECONDS", str(5 * 60 * 60 + 30 * 60))
)

celery_app = Celery(
    "drone_backend",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

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
    task_routes={
        "photogrammetry.process_job": {"queue": CELERY_PHOTOGRAMMETRY_QUEUE},
        "warehouse_mapping.process_job": {"queue": CELERY_WAREHOUSE_MAPPING_QUEUE},
        "video_analysis.process_job": {"queue": CELERY_VIDEO_ANALYSIS_QUEUE},
    },
    worker_max_tasks_per_child=CELERY_WORKER_MAX_TASKS_PER_CHILD,
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
}
celery_app.conf.timezone = "UTC"
