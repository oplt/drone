"""Warehouse mapping stack lifecycle — shared helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.modules.warehouse.ports import WarehousePerceptionCommandResult
from backend.modules.warehouse.service.readiness_result import WarehouseReadinessResult

from . import deps
from .models import WarehouseMappingStackStatus

if TYPE_CHECKING:
    from backend.modules.warehouse.service.live_map_readiness import MappingReadinessResult


def mapping_stack_not_running_result() -> WarehousePerceptionCommandResult:
    return WarehousePerceptionCommandResult(
        accepted=False,
        status="mapping_stack_not_running",
        detail="Warehouse mapping stack is not running.",
    )


def _merge_nvblox_readiness_from_rgbd(
    flight_readiness: WarehouseReadinessResult,
    rgbd_readiness: MappingReadinessResult,
) -> WarehouseReadinessResult:
    if flight_readiness.nvblox_ready:
        return flight_readiness
    if not rgbd_readiness.ready or not rgbd_readiness.nvblox_pointcloud_topics:
        return flight_readiness
    return WarehouseReadinessResult(
        **{
            **flight_readiness.to_dict(),
            "nvblox_ready": True,
            "ready": bool(flight_readiness.core_ready),
            "missing_nvblox_topics": [],
            "detail": None,
        }
    )


def _is_mapping_stack_process_running() -> bool:
    process = deps.resolve("_mapping_stack_process")
    return process is not None and process.returncode is None


def _mapping_stack_pid() -> int | None:
    process = deps.resolve("_mapping_stack_process")
    if process is None:
        return None
    return process.pid


def _stack_status_field(name: str):
    return deps.resolve(name)


__all__ = [
    "WarehouseMappingStackStatus",
    "_is_mapping_stack_process_running",
    "_mapping_stack_pid",
    "_merge_nvblox_readiness_from_rgbd",
    "_stack_status_field",
    "mapping_stack_not_running_result",
]
