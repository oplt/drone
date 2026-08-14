from __future__ import annotations

import inspect
import re
from pathlib import Path

import yaml

from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.agriculture.routers import live as agriculture_live
from backend.modules.telemetry import websocket_api

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "docker-compose.yml"
VIDEO_STATUS_INDEX_MIGRATION = (
    ROOT
    / "backend/infrastructure/persistence/alembic/versions/k4l5m6n7o8p9_video_status_indexes.py"
)


def _compose_worker_queues() -> set[str]:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    queues: set[str] = set()
    for name, service in compose.get("services", {}).items():
        if not name.startswith("worker"):
            continue
        command = service.get("command", "")
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        match = re.search(r"--queues=([^\s]+)", str(command))
        if match:
            queues.update(part.strip() for part in match.group(1).split(",") if part.strip())
    return queues


def test_celery_task_routes_map_to_compose_worker_queues() -> None:
    listened_queues = _compose_worker_queues()
    assert "default" in listened_queues

    missing: dict[str, str] = {}
    for task_name, route in celery_app.conf.task_routes.items():
        queue = route["queue"]
        if queue not in listened_queues:
            missing[task_name] = queue

    assert not missing, f"Celery routes without compose listeners: {missing}"


def test_video_status_index_migration_declares_hot_path_indexes() -> None:
    source = VIDEO_STATUS_INDEX_MIGRATION.read_text(encoding="utf-8")
    assert "ix_video_assets_status" in source
    assert "ix_video_analysis_jobs_status" in source
    assert "ix_video_analysis_jobs_status_lease" in source


def test_telemetry_websocket_rejects_query_string_tokens() -> None:
    source = inspect.getsource(websocket_api._authenticate_websocket)
    assert 'query_params.get("token")' in source
    assert "Query-string tokens are not allowed" in source


def test_live_advisory_offloads_blocking_work() -> None:
    source = inspect.getsource(agriculture_live.live_advisory)
    assert "run_blocking" in source
    assert 'operation="agriculture_live_advisory"' in source
