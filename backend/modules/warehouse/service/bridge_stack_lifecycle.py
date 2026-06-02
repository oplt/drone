from __future__ import annotations

import os

from backend.modules.warehouse.service.bridge_supervisor import (
    WarehouseBridgeSupervisorStatus,
    get_warehouse_bridge_supervisor,
)


def _autostart_enabled() -> bool:
    return os.getenv("WAREHOUSE_PREFLIGHT_AUTOSTART_BRIDGE", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def ensure_warehouse_bridge_stack_for_preflight() -> WarehouseBridgeSupervisorStatus | None:
    if not _autostart_enabled():
        return None

    # Preflight must return a go/no-go payload, not block until every ROS/Gazebo
    # topic is already ready. Start the stack and wait only for the bridge
    # health endpoint; evaluate_warehouse_go_preflight then performs the deep
    # snapshot and reports blockers to the UI.
    return await get_warehouse_bridge_supervisor().ensure_ready(deep=False)


async def warehouse_bridge_stack_status() -> WarehouseBridgeSupervisorStatus:
    return await get_warehouse_bridge_supervisor().status()


async def reset_warehouse_bridge_stack() -> WarehouseBridgeSupervisorStatus:
    return await get_warehouse_bridge_supervisor().reset()
