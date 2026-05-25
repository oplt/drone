from backend.entrypoints.workers.celery_app import celery_app

# Ensure named workers and beat tasks are registered on worker import.
from . import (
    deliverable_tasks,
    export_tasks,
    outbox_tasks,
    photogrammetry_tasks,
    scheduling_tasks,
    webhook_tasks,
)

__all__ = ["celery_app"]
