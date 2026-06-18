from __future__ import annotations


def test_warehouse_structure_task_registered_on_worker_entrypoint_import() -> None:
    from backend.entrypoints.workers.celery_app import celery_app
    from backend.modules.warehouse.service.structure_jobs import EXTRACTION_TASK_NAME

    assert EXTRACTION_TASK_NAME in celery_app.tasks
