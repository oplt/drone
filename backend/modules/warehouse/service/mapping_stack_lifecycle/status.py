"""Warehouse mapping stack lifecycle — status probes."""

from __future__ import annotations

import logging

from backend.observability.instruments import observed_span, structured_error

from . import deps
from .helpers import (
    _is_mapping_stack_process_running,
    _mapping_stack_pid,
    _stack_status_field,
)
from .models import WarehouseMappingStackStatus
from .nvblox_log_parser import _get_nvblox_log_parser
from .start import _maybe_start_mapping_stack_cmd

logger = logging.getLogger(__name__)


async def get_mapping_stack_status() -> WarehouseMappingStackStatus:
    try:
        return await deps.resolve("_get_mapping_stack_status_impl")()
    except Exception as exc:
        logger.warning(
            "Mapping stack status probe failed; returning degraded status: %s",
            exc,
            exc_info=True,
        )
        nvblox_log_parser = _get_nvblox_log_parser()
        return WarehouseMappingStackStatus(
            running=_is_mapping_stack_process_running(),
            pid=_mapping_stack_pid(),
            started_at=_stack_status_field("_mapping_stack_started_at"),
            last_exit_code=_stack_status_field("_mapping_stack_last_exit_code"),
            last_error=str(exc),
            nvblox_running=False,
            phase="degraded",
            nvblox_health={"log_parser": nvblox_log_parser.as_dict()},
        )


async def _get_mapping_stack_status_impl() -> WarehouseMappingStackStatus:
    from backend.modules.warehouse.service.live_map_bridge import (
        live_map_bridge_status,
    )
    from backend.modules.warehouse.service.warehouse_preflight import (
        fetch_warehouse_perception_status,
    )
    from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
    from backend.modules.warehouse.service.readiness_result import (
        readiness_from_perception_status_strict,
    )

    status = await fetch_warehouse_perception_status(deep=True, force=False)
    flight_readiness = readiness_from_perception_status_strict(status)
    bridge = live_map_bridge_status()

    process_running = _is_mapping_stack_process_running()

    nvblox_log_parser = _get_nvblox_log_parser()
    nvblox_status_tracker.note_process_running(process_running)
    last_error_state = _stack_status_field("_mapping_stack_last_error")
    if last_error_state and not process_running:
        nvblox_status_tracker.note_error(last_error_state)

    running = bool(
        process_running
        or status.reachable
        or status.configured
        or bridge.get("running")
        or flight_readiness.core_ready
    )

    tf_degraded = nvblox_status_tracker.tf_degraded()
    nvblox_health: dict[str, object] = {
        **nvblox_status_tracker.as_dict(),
        "log_parser": nvblox_log_parser.as_dict(),
    }

    if tf_degraded and process_running:
        phase = "degraded"
    elif flight_readiness.nvblox_ready and not tf_degraded:
        phase = "ready"
    elif running:
        phase = "starting"
    else:
        phase = "stopped"

    last_error = None
    if tf_degraded:
        last_error = (
            f"nvblox TF degraded "
            f"(TF_OLD_DATA={nvblox_status_tracker.tf_old_data_count}, "
            f"jump_back={nvblox_status_tracker.tf_jump_back_count})"
        )
    elif not running:
        last_error = status.detail or last_error_state
    elif last_error_state and not flight_readiness.nvblox_ready:
        last_error = last_error_state

    nvblox_running = bool(flight_readiness.nvblox_ready and not tf_degraded)

    return WarehouseMappingStackStatus(
        running=running,
        pid=_mapping_stack_pid(),
        started_at=_stack_status_field("_mapping_stack_started_at"),
        last_exit_code=_stack_status_field("_mapping_stack_last_exit_code"),
        last_error=last_error,
        nvblox_running=nvblox_running,
        phase=phase,
        tf_degraded=tf_degraded,
        nvblox_health=nvblox_health,
    )


async def start_warehouse_mapping_stack() -> WarehouseMappingStackStatus:
    """Start nvblox using the same launcher path used by warehouse scans."""
    with observed_span(
        "mapping.stack.start",
        ros_topic="/warehouse/front/rgbd/points",
        **{"mapping.layer": "nvblox"},
    ):
        try:
            await _maybe_start_mapping_stack_cmd()
        except Exception as exc:
            structured_error(
                logger,
                "mapping_stack_start_failed",
                exc,
                ros_topic="/warehouse/front/rgbd/points",
            )
        return await get_mapping_stack_status()


__all__ = [
    "_get_mapping_stack_status_impl",
    "get_mapping_stack_status",
    "start_warehouse_mapping_stack",
]
