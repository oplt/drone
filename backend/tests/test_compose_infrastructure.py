from __future__ import annotations

import re
from pathlib import Path

import yaml

from backend.core.config.runtime import settings

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "docker-compose.yml"
GPU_COMPOSE_PATH = ROOT / "docker-compose.gpu.yml"


def _expected_agriculture_queues() -> set[str]:
    return {
        settings.celery_agriculture_ingest_queue,
        settings.celery_agriculture_quality_queue,
        settings.celery_agriculture_inference_queue,
        settings.celery_agriculture_segmentation_queue,
        settings.celery_agriculture_geospatial_queue,
        settings.celery_agriculture_temporal_queue,
        settings.celery_agriculture_fusion_queue,
        settings.celery_agriculture_exports_queue,
        settings.celery_agriculture_dead_letter_queue,
    }


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _command_text(service: dict) -> str:
    command = service.get("command", "")
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command)


def _worker_queue_names(compose: dict) -> set[str]:
    queues: set[str] = set()
    for name, service in compose.get("services", {}).items():
        if not name.startswith("worker"):
            continue
        match = re.search(r"--queues=([^\s]+)", _command_text(service))
        if match:
            queues.update(part.strip() for part in match.group(1).split(",") if part.strip())
    return queues


def test_compose_migrate_service_runs_before_api() -> None:
    compose = _load_compose(COMPOSE_PATH)
    migrate = compose["services"]["migrate"]
    api = compose["services"]["api"]

    assert "alembic" in _command_text(migrate)
    assert "upgrade head" in _command_text(migrate)
    assert migrate.get("restart") == "no"
    assert api["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert "alembic" not in _command_text(api)
    assert "uvicorn" in _command_text(api)


def test_compose_agriculture_workers_listen_to_celery_routes() -> None:
    compose = _load_compose(COMPOSE_PATH)
    listened_queues = _worker_queue_names(compose)

    assert "worker-agriculture-ingest" in compose["services"]
    assert "worker-agriculture-inference" in compose["services"]

    expected_queues = _expected_agriculture_queues()
    missing = expected_queues - listened_queues
    assert not missing, f"No compose worker listens to agriculture queues: {missing}"


def test_gpu_compose_profile_reserves_devices_for_inference_workers() -> None:
    gpu_compose = _load_compose(GPU_COMPOSE_PATH)
    services = gpu_compose["services"]
    for name in ("worker-video", "worker-vision", "worker-agriculture-inference"):
        device_requests = services[name]["device_requests"]
        assert device_requests[0]["driver"] == "nvidia"
        assert device_requests[0]["capabilities"] == ["gpu"]
