from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends

from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import require_user
from backend.modules.identity.models import User
from backend.modules.missions.repository import mission_runtime_repo
from backend.modules.telemetry.api.telemetry_route_support import (
    OPS_HEALTH_QUEUE_LABELS,
    RECENT_TELEMETRY_THRESHOLD_SEC,
    collect_ops_health_alerts,
    ops_health_overall_status,
    queue_snapshot,
    telemetry_update_age,
)
from backend.modules.vehicle_runtime.factory import build_orchestrator as _build_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telemetry"])


@router.get("/runtime-metrics")
async def get_runtime_metrics(user: User = Depends(require_user)) -> Any:
    """Return live orchestrator runtime metrics: queue depths, dropped counts, ingest rate."""
    orch = await _build_orchestrator()
    return orch.get_runtime_metrics()


@router.get("/shadow-report")
async def get_shadow_report(user: User = Depends(require_user)) -> Any:
    """Compare old direct-DB-write path vs new queued path under shadow mode.

    Shadow mode is enabled by setting ORCHESTRATOR_SHADOW_MODE=true in the
    environment. When active, both paths run simultaneously so you can verify
    the new path is stable before fully removing the legacy write.
    Once error rates are equivalent, set ORCHESTRATOR_SHADOW_MODE=false and
    mark the shadow tasks done in todos.txt.
    """
    orch = await _build_orchestrator()
    return orch.get_shadow_report()


@router.get("/ops-health")
async def get_ops_health(user: User = Depends(require_user)) -> dict[str, Any]:
    """Return a customer-visible operational health snapshot."""
    orch = await _build_orchestrator()
    telemetry = telemetry_manager.runtime_snapshot()
    runtime_metrics = orch.get_runtime_metrics()
    shadow_report = orch.get_shadow_report()
    labeled_queue_snapshots = {
        label: queue_snapshot(runtime_metrics, prefix)
        for label, prefix in OPS_HEALTH_QUEUE_LABELS.items()
    }

    now = time.time()
    last_update = float(telemetry["last_update"] or 0.0)
    telemetry_age = telemetry_update_age(last_update, now)
    has_recent_update = (
        telemetry_age is not None and telemetry_age <= RECENT_TELEMETRY_THRESHOLD_SEC
    )

    video_status: dict[str, object] = {"available": False}
    if getattr(orch, "video", None) is not None:
        try:
            status = dict(orch.video.get_connection_status())
            video_status = {
                "available": True,
                "healthy": bool(status.get("healthy")),
                "frame_count": int(status.get("frame_count") or 0),
                "fps": float(status.get("fps") or 0.0),
                "resolution": str(status.get("resolution") or ""),
                "recording": bool(status.get("recording")),
                "recording_file": status.get("recording_file"),
            }
        except Exception as exc:  # pragma: no cover - defensive read path
            logger.warning("Failed to read video health snapshot: %s", exc)
            video_status = {
                "available": True,
                "healthy": False,
                "error": "Video health unavailable",
            }

    active_mission = None
    active_db_row = await mission_runtime_repo.get_active()
    if active_db_row is not None and int(active_db_row.user_id or 0) == int(user.id):
        active_mission = {
            "flight_id": active_db_row.client_flight_id,
            "mission_name": active_db_row.mission_name,
            "mission_type": active_db_row.mission_type,
            "state": active_db_row.state,
            "updated_at": (
                active_db_row.updated_at.timestamp()
                if getattr(active_db_row, "updated_at", None) is not None
                else None
            ),
        }

    alerts = collect_ops_health_alerts(
        telemetry=telemetry,
        has_recent_update=has_recent_update,
        runtime_metrics=runtime_metrics,
        labeled_queue_snapshots=labeled_queue_snapshots,
        shadow_report=shadow_report,
        video_status=video_status,
    )

    return {
        "status": ops_health_overall_status(alerts, bool(telemetry["source_connected"])),
        "generated_at": now,
        "telemetry": {
            "running": telemetry["running"],
            "source_connected": telemetry["source_connected"],
            "active_connections": telemetry["active_connections"],
            "last_update": last_update,
            "last_update_age_sec": telemetry_age,
            "has_recent_update": has_recent_update,
            "recent_threshold_sec": RECENT_TELEMETRY_THRESHOLD_SEC,
        },
        "video": video_status,
        "queues": {
            "db_event": labeled_queue_snapshots["flight events"],
            "db_lifecycle": labeled_queue_snapshots["mission lifecycle"],
            "raw_event": labeled_queue_snapshots["raw ingest"],
        },
        "runtime_metrics": runtime_metrics,
        "shadow": shadow_report,
        "active_mission": active_mission,
        "alerts": alerts,
    }
