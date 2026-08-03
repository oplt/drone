"""Worker boundary; Celery wiring can enqueue this without coupling API routes."""

from typing import Any


def analysis_job_payload(*, flight_id: str, idempotency_key: str) -> dict[str, Any]:
    return {"task": "agriculture.analysis", "flight_id": flight_id, "idempotency_key": idempotency_key}
