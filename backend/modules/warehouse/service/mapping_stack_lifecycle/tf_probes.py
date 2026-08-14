"""Warehouse mapping stack lifecycle — TF/sim-time readiness probes."""

from __future__ import annotations

import logging

from .nvblox_log_parser import _OptionalProbeResult

logger = logging.getLogger(__name__)


def _note_mapping_startup(mark: str) -> None:
    from backend.modules.warehouse.service.startup_timing_hooks import note_mapping_startup_safe

    note_mapping_startup_safe(mark)


async def _kill_stale_nvblox_processes(keep_pgids: set[int] | None = None) -> None:
    try:
        from backend.modules.warehouse.service.sim_time_tf_readiness import (
            kill_stale_nvblox_processes,
        )

        await kill_stale_nvblox_processes(keep_pgids=keep_pgids)
    except ModuleNotFoundError as exc:
        logger.warning("Optional TF readiness cleanup unavailable: %s", exc)


async def _probe_clock_monotonic() -> _OptionalProbeResult:
    try:
        from backend.modules.warehouse.service.sim_time_tf_readiness import (
            probe_clock_monotonic,
        )

        return await probe_clock_monotonic()
    except ModuleNotFoundError:
        return _OptionalProbeResult()


async def _probe_tf_broadcasters() -> _OptionalProbeResult:
    try:
        from backend.modules.warehouse.service.sim_time_tf_readiness import (
            probe_tf_broadcasters,
        )

        return await probe_tf_broadcasters()
    except ModuleNotFoundError:
        return _OptionalProbeResult()


async def _wait_for_tf_stable(*, timeout_s: float) -> _OptionalProbeResult:
    try:
        from backend.modules.warehouse.service.sim_time_tf_readiness import (
            wait_for_tf_stable,
        )

        return await wait_for_tf_stable(timeout_s=timeout_s)
    except ModuleNotFoundError:
        return _OptionalProbeResult()


__all__ = [
    "_kill_stale_nvblox_processes",
    "_note_mapping_startup",
    "_probe_clock_monotonic",
    "_probe_tf_broadcasters",
    "_wait_for_tf_stable",
]
