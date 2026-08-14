"""Warehouse mapping stack lifecycle — shutdown and process stop."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import signal

from backend.observability.instruments import observed_span, structured_error

from . import deps
from .tf_probes import _kill_stale_nvblox_processes

logger = logging.getLogger(__name__)


async def _stop_mapping_stack_process(*, strict: bool = False) -> bool:
    """
    Stop the Nvblox mapping stack process.

    Returns:
        True  -> process was stopped or already gone
        False -> cleanup had a non-fatal problem

    strict=True can be used in tests/admin commands if you want cleanup errors
    to fail loudly. Mission shutdown should normally use strict=False.
    """
    async with deps.resolve("_mapping_stack_lock"):
        process = deps.resolve("_mapping_stack_process")
    if process is None:
        return True

    pid = getattr(process, "pid", None)

    try:
        if process.returncode is not None:
            logger.info("Nvblox mapping stack already stopped pid=%s", pid)
            async with deps.resolve("_mapping_stack_lock"):
                if deps.resolve("_mapping_stack_process") is process:
                    deps.set_state("_mapping_stack_process", None)
            return True

        logger.info("Stopping Nvblox mapping stack process pid=%s", pid)

        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            logger.info("Nvblox process group already gone pid=%s", pid)
            async with deps.resolve("_mapping_stack_lock"):
                if deps.resolve("_mapping_stack_process") is process:
                    deps.set_state("_mapping_stack_process", None)
            return True
        except Exception:
            logger.warning(
                "Failed to send SIGTERM to Nvblox process group pid=%s",
                pid,
                exc_info=True,
            )
            if strict:
                raise
            return False

        try:
            await asyncio.wait_for(process.wait(), timeout=8.0)
            logger.info("Nvblox mapping stack stopped pid=%s", pid)
            return True

        except TimeoutError:
            logger.warning(
                "Nvblox mapping stack did not stop after SIGTERM; sending SIGKILL pid=%s",
                pid,
            )

            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                logger.info("Nvblox process group already gone before SIGKILL pid=%s", pid)
                return True
            except Exception:
                logger.warning(
                    "Failed to send SIGKILL to Nvblox process group pid=%s",
                    pid,
                    exc_info=True,
                )
                if strict:
                    raise
                return False

            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
                logger.info("Nvblox mapping stack killed pid=%s", pid)
                return True
            except Exception:
                logger.warning(
                    "Failed while waiting for killed Nvblox process pid=%s",
                    pid,
                    exc_info=True,
                )
                if strict:
                    raise
                return False

    except Exception:
        logger.warning(
            "Non-fatal error while stopping Nvblox mapping stack pid=%s",
            pid,
            exc_info=True,
        )
        if strict:
            raise
        return False

    finally:
        async with deps.resolve("_mapping_stack_lock"):
            if deps.resolve("_mapping_stack_process") is process:
                deps.set_state("_mapping_stack_process", None)


async def shutdown_warehouse_mapping_stack() -> None:
    from backend.modules.warehouse.service.live_map_bridge import (
        stop_warehouse_live_map_bridge,
    )
    from backend.modules.warehouse.service.provisional_mapping import clear_provisional_epochs

    with observed_span(
        "mapping.stack.stop",
        ros_topic="/warehouse/front/rgbd/points",
        **{"mapping.layer": "nvblox"},
    ):
        from backend.modules.warehouse.service.live_map_readiness import invalidate_readiness_caches

        invalidate_readiness_caches()
        try:
            await stop_warehouse_live_map_bridge()
        except Exception as exc:
            structured_error(
                logger,
                "live_map_bridge_stop_failed",
                exc,
                ros_topic="/warehouse/front/rgbd/points",
            )
        await _stop_mapping_stack_process()
        await _kill_stale_nvblox_processes()
        clear_provisional_epochs()

    background_tasks = deps.resolve("_background_tasks")
    if background_tasks:
        for task in tuple(background_tasks):
            task.cancel()
        await asyncio.gather(*tuple(background_tasks), return_exceptions=True)

    settings = deps.resolve("settings")
    shutdown_cmd = str(getattr(settings, "warehouse_shutdown_mapping_stack_cmd", "") or "").strip()
    if shutdown_cmd:
        try:
            shutdown_argv = shlex.split(shutdown_cmd)
            if not shutdown_argv:
                return
            await asyncio.to_thread(
                __import__("subprocess").run,
                shutdown_argv,
                shell=False,
                check=False,
                timeout=10,
            )
        except Exception:
            logger.warning("Non-fatal error while running mapping shutdown command", exc_info=True)


__all__ = ["_stop_mapping_stack_process", "shutdown_warehouse_mapping_stack"]
