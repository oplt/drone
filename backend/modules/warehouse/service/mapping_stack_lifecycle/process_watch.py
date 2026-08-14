"""Warehouse mapping stack lifecycle — process logging and TF restart watcher."""

from __future__ import annotations

import asyncio
import logging
import signal
import time

from . import deps
from .background_tasks import _track_background_task
from .nvblox_log_parser import _get_nvblox_log_parser
from .settings_helpers import _setting_float, _setting_int
from .tf_probes import (
    _kill_stale_nvblox_processes,
    _probe_clock_monotonic,
    _wait_for_tf_stable,
)

logger = logging.getLogger(__name__)


def _log_nvblox_line(prefix: str, line: str) -> None:
    nvblox_log_parser = _get_nvblox_log_parser()
    level, emit = nvblox_log_parser.ingest(line)
    if not emit:
        if nvblox_log_parser.should_restart_for_tf_instability(
            jump_threshold=_setting_int("warehouse_nvblox_tf_restart_jump_threshold", 3),
            cooldown_s=_setting_float("warehouse_nvblox_tf_restart_cooldown_s", 30.0),
            last_restart_at=deps.resolve("_last_nvblox_restart_at"),
        ):
            _track_background_task(asyncio.create_task(_restart_mapping_stack_for_tf()))
        return

    text = line.rstrip()
    if level >= logging.ERROR:
        logger.error("[%s] %s", prefix, text)
    elif level >= logging.WARNING:
        logger.warning("[%s] %s", prefix, text)
    else:
        logger.info("[%s] %s", prefix, text)


async def _log_process_stream(
    stream: asyncio.StreamReader | None,
    *,
    prefix: str,
) -> None:
    if stream is None:
        return

    while True:
        line = await stream.readline()
        if not line:
            break

        _log_nvblox_line(prefix, line.decode(errors="replace"))


async def _restart_mapping_stack_for_tf() -> None:
    if deps.resolve("_restart_in_progress"):
        return

    nvblox_log_parser = _get_nvblox_log_parser()
    deps.set_state("_restart_in_progress", True)
    try:
        from .shutdown import _stop_mapping_stack_process
        from .start import _maybe_start_mapping_stack_cmd

        logger.warning(
            "Restarting nvblox mapping stack due to TF/sim-time instability "
            "(jump_back=%d tf_old_data=%d)",
            nvblox_log_parser.tf_jump_back_count,
            nvblox_log_parser.tf_old_data_count,
        )
        await _stop_mapping_stack_process()
        await asyncio.sleep(1.0)
        await _kill_stale_nvblox_processes()
        clock = await _probe_clock_monotonic()
        if not clock.ok:
            logger.warning("Clock still not monotonic before nvblox restart: %s", clock.to_dict())
        tf = await _wait_for_tf_stable(timeout_s=_setting_float("warehouse_preflight_tf_wait_s", 10.0))
        if not tf.ok:
            logger.warning("TF still unstable before nvblox restart: %s", tf.to_dict())

        nvblox_log_parser.note_restart()
        deps.set_state("_last_nvblox_restart_at", time.monotonic())
        await _maybe_start_mapping_stack_cmd(skip_stale_kill=True)
    except Exception:
        logger.exception("Failed to restart nvblox after TF instability")
    finally:
        deps.set_state("_restart_in_progress", False)


async def _watch_mapping_stack_process(
    process: asyncio.subprocess.Process,
) -> None:
    exit_code = await process.wait()

    if deps.resolve("_mapping_stack_process") is process:
        deps.set_state("_mapping_stack_last_exit_code", exit_code)

        if exit_code in (0, -signal.SIGTERM, signal.SIGTERM, 143):
            logger.info(
                "Nvblox mapping stack process exited normally with code %s.",
                exit_code,
            )
        else:
            if not deps.resolve("_mapping_stack_last_error"):
                deps.set_state(
                    "_mapping_stack_last_error",
                    f"Nvblox mapping stack exited with code {exit_code}.",
                )
            logger.warning(
                "Nvblox mapping stack process exited with code %s.",
                exit_code,
            )
            _track_background_task(asyncio.create_task(_kill_stale_nvblox_processes()))


__all__ = [
    "_log_nvblox_line",
    "_log_process_stream",
    "_restart_mapping_stack_for_tf",
    "_watch_mapping_stack_process",
]
