"""Warehouse mapping stack lifecycle — public package API."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.core.config.runtime import settings

from .helpers import (
    _is_mapping_stack_process_running,
    _mapping_stack_pid,
    _merge_nvblox_readiness_from_rgbd,
    mapping_stack_not_running_result,
)
from .models import WarehouseMappingStackStatus
from .scan_prep import prepare_warehouse_scan_ros
from .shutdown import _stop_mapping_stack_process, shutdown_warehouse_mapping_stack
from .start import _maybe_start_mapping_stack_cmd
from .status import (
    _get_mapping_stack_status_impl,
    get_mapping_stack_status,
    start_warehouse_mapping_stack,
)

_mapping_stack_process: asyncio.subprocess.Process | None = None
_mapping_stack_started_at: str | None = None
_mapping_stack_last_exit_code: int | None = None
_mapping_stack_last_error: str | None = None
_mapping_stack_lock = asyncio.Lock()
_last_nvblox_restart_at: float = 0.0
_restart_in_progress = False
_background_tasks: set[asyncio.Task[Any]] = set()

__all__ = [
    "WarehouseMappingStackStatus",
    "_background_tasks",
    "_get_mapping_stack_status_impl",
    "_is_mapping_stack_process_running",
    "_last_nvblox_restart_at",
    "_mapping_stack_last_error",
    "_mapping_stack_last_exit_code",
    "_mapping_stack_lock",
    "_mapping_stack_pid",
    "_mapping_stack_process",
    "_mapping_stack_started_at",
    "_maybe_start_mapping_stack_cmd",
    "_merge_nvblox_readiness_from_rgbd",
    "_restart_in_progress",
    "_stop_mapping_stack_process",
    "get_mapping_stack_status",
    "mapping_stack_not_running_result",
    "prepare_warehouse_scan_ros",
    "settings",
    "shutdown_warehouse_mapping_stack",
    "start_warehouse_mapping_stack",
]
