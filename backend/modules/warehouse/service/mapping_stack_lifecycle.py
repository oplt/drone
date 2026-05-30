from __future__ import annotations

import asyncio
import logging

from backend.infrastructure.warehouse.mapping_stack_process import (
    MappingStackStatus,
    get_warehouse_mapping_stack_manager,
)
from backend.modules.warehouse.ports import WarehousePerceptionCommandResult

logger = logging.getLogger(__name__)


async def ensure_warehouse_mapping_stack_running() -> MappingStackStatus:
    manager = get_warehouse_mapping_stack_manager()
    return await asyncio.to_thread(manager.start)


async def shutdown_warehouse_mapping_stack() -> MappingStackStatus:
    manager = get_warehouse_mapping_stack_manager()
    return await asyncio.to_thread(manager.stop)


async def warehouse_mapping_stack_status() -> MappingStackStatus:
    manager = get_warehouse_mapping_stack_manager()
    return await asyncio.to_thread(manager.status)


def mapping_stack_not_running_result() -> WarehousePerceptionCommandResult:
    return WarehousePerceptionCommandResult(
        accepted=False,
        status="mapping_stack_unavailable",
        detail="Warehouse ROS mapping stack is not running",
    )
