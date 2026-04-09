from backend.tasks.celery_app import celery_app

# Ensure task modules are imported when this package is loaded.
from . import photogrammetry_tasks

__all__ = ["celery_app"]
