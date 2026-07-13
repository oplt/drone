from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.config.runtime import settings
from backend.core.database.session import engine
from backend.observability import prometheus_metrics


async def _database_ready() -> tuple[bool, str | None]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, type(exc).__name__


async def _object_storage_ready() -> tuple[bool, str | None]:
    backend = str(getattr(settings, "storage_backend", "local") or "local").lower()
    if backend != "s3":
        # Local storage is process-owned; only verify the configured roots are
        # present. This stays cheap and does not make liveness depend on disk.
        roots = (
            Path(settings.irrigation_storage_dir),
            Path(settings.PHOTOGRAMMETRY_STORAGE_DIR),
        )
        return all(root.exists() and root.is_dir() for root in roots), None
    try:
        from backend.infrastructure.storage import ObjectStorageClient

        await asyncio.wait_for(
            ObjectStorageClient().check_bucket(),
            timeout=max(0.1, float(settings.observability_health_timeout_s)),
        )
        return True, None
    except Exception as exc:
        return False, type(exc).__name__


async def _optional_service_readiness() -> dict[str, dict[str, Any]]:
    """Probe optional integrations without making them required dependencies."""
    checks: dict[str, dict[str, Any]] = {}

    ros_workspace_raw = str(getattr(settings, "warehouse_ros2_ws", "") or "").strip()
    ros_workspace = Path(ros_workspace_raw) if ros_workspace_raw else Path()
    checks["ros"] = {
        "configured": bool(ros_workspace_raw),
        "ready": ros_workspace.exists() if ros_workspace_raw else False,
        "required": False,
    }

    try:
        from backend.infrastructure.messaging.websocket_publisher import telemetry_manager

        snapshot = telemetry_manager.runtime_snapshot()
        checks["mavlink"] = {
            "configured": bool(getattr(settings, "drone_conn", "")),
            "ready": bool(snapshot.get("source_connected")),
            "required": False,
        }
    except Exception as exc:
        checks["mavlink"] = {
            "configured": bool(getattr(settings, "drone_conn", "")),
            "ready": False,
            "required": False,
            "error": type(exc).__name__,
        }

    webodm_url = str(getattr(settings, "WEBODM_BASE_URL", "") or "").strip()
    if not webodm_url or bool(getattr(settings, "WEBODM_MOCK_MODE", False)):
        checks["webodm"] = {
            "configured": bool(webodm_url),
            "ready": bool(getattr(settings, "WEBODM_MOCK_MODE", False)),
            "required": False,
        }
    else:
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    max(0.1, float(settings.observability_health_timeout_s))
                )
            ) as client:
                response = await client.get(f"{webodm_url.rstrip('/')}/")
            checks["webodm"] = {
                "configured": True,
                "ready": response.status_code < 500,
                "status_code": response.status_code,
                "required": False,
            }
        except Exception as exc:
            checks["webodm"] = {
                "configured": True,
                "ready": False,
                "error": type(exc).__name__,
                "required": False,
            }
    return checks


def _celery_workers_by_queue() -> dict[str, int]:
    try:
        from backend.entrypoints.workers.celery_app import celery_app

        responses = celery_app.control.inspect(timeout=0.75).active_queues() or {}
    except Exception:
        responses = {}
    counts = {queue: 0 for queue in prometheus_metrics.KNOWN_QUEUES}
    for queues in responses.values():
        for queue in queues or []:
            name = str(queue.get("name") or "")
            if name in counts:
                counts[name] += 1
    for queue, count in counts.items():
        prometheus_metrics.celery_workers_ready.labels(queue=queue).set(count)
    return counts


async def dependency_readiness() -> tuple[bool, dict[str, Any]]:
    broker_url = str(settings.celery_broker_url or "")
    if not broker_url.startswith(("redis://", "rediss://")):
        return False, {"redis_broker": {"ready": False, "error": "unsupported broker URL"}}

    try:
        import redis.asyncio as redis

        client = redis.from_url(
            broker_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            await asyncio.wait_for(client.ping(), timeout=1.5)
        finally:
            await client.aclose()
    except Exception as exc:
        return False, {
            "redis_broker": {
                "ready": False,
                "error": type(exc).__name__,
            }
        }
    database_ready, database_error = await _database_ready()
    try:
        workers = await asyncio.wait_for(
            asyncio.to_thread(_celery_workers_by_queue),
            timeout=max(0.1, float(settings.observability_health_timeout_s)),
        )
    except TimeoutError:
        workers = {queue: 0 for queue in prometheus_metrics.KNOWN_QUEUES}
    object_storage_ready, object_storage_error = await _object_storage_ready()
    optional = await _optional_service_readiness()
    details = {
        "redis_broker": {"ready": True},
        "database": {"ready": database_ready, "error": database_error},
        "object_storage": {
            "ready": object_storage_ready,
            "error": object_storage_error,
            "required": str(getattr(settings, "storage_backend", "local")).lower() == "s3",
        },
        "celery_workers": {
            "ready": all(workers.values()),
            "queues": workers,
        },
        "optional": optional,
    }
    return database_ready and object_storage_ready and all(workers.values()), details
