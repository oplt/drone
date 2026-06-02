from __future__ import annotations

import os

from backend.core.config.runtime import settings
from backend.infrastructure.warehouse.bridge_stack_process import (
    get_warehouse_bridge_stack_manager,
)
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.warehouse_preflight import (
    fetch_warehouse_perception_status,
)


def _idle_probe_enabled() -> bool:
    return os.getenv("WAREHOUSE_IDLE_BRIDGE_PROBE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _idle_status() -> WarehousePerceptionStatus:
    bridge_url = settings.WAREHOUSE_ROS_BRIDGE_URL.strip()
    websocket_url = settings.WAREHOUSE_ROS_WS_URL.strip()
    capture_root = settings.WAREHOUSE_ROS_CAPTURE_ROOT.strip()
    profile = settings.WAREHOUSE_ROS_PROFILE.strip() or "gazebo"
    return WarehousePerceptionStatus(
        configured=bool(bridge_url),
        reachable=True,
        ready=False,
        status="idle",
        profile=profile,
        bridge_url=bridge_url or None,
        websocket_url=websocket_url or None,
        capture_root=capture_root,
        detail="Warehouse ROS bridge starts when Warehouse Preflight runs.",
        components={
            "bridge_idle": True,
            "app_health_only": True,
            "preflight_path": "/warehouse/preflight",
            "nvblox_deferred": True,
            "nvblox_checks_active": False,
        },
    )


async def fetch_idle_warehouse_perception_status() -> WarehousePerceptionStatus:
    if _idle_probe_enabled():
        return await fetch_warehouse_perception_status(deep=False, force=False)

    stack_status = get_warehouse_bridge_stack_manager().status()
    if not stack_status.running:
        return _idle_status()
    return await fetch_warehouse_perception_status(deep=False, force=False)
