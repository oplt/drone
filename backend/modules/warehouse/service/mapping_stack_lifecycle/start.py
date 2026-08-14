"""Warehouse mapping stack lifecycle — start nvblox mapping stack."""

from __future__ import annotations

import asyncio
import logging
import time
from asyncio.subprocess import PIPE
from datetime import UTC, datetime

from . import deps
from .background_tasks import _track_background_task
from .helpers import _is_mapping_stack_process_running, _mapping_stack_pid
from .launch import _build_nvblox_launch_command
from .nvblox_log_parser import _get_nvblox_log_parser
from .settings_helpers import _setting_float
from .tf_probes import (
    _kill_stale_nvblox_processes,
    _note_mapping_startup,
    _probe_clock_monotonic,
    _probe_tf_broadcasters,
    _wait_for_tf_stable,
)

logger = logging.getLogger(__name__)


async def _maybe_start_mapping_stack_cmd(*, skip_stale_kill: bool = False) -> None:
    """
    Start the Nvblox mapping stack through ROS 2 launch.

    This function intentionally keeps the old name because
    prepare_warehouse_scan_ros() already calls it.

    Important:
        Do not use subprocess.run(..., timeout=30) for Nvblox.
        Nvblox is a long-running ROS process. If it starts correctly,
        it should stay alive until shutdown.
    """
    if _is_mapping_stack_process_running():
        logger.info(
            "Nvblox mapping stack already running (pid=%s); reusing warm stack.",
            _mapping_stack_pid(),
        )
        return

    if not skip_stale_kill:
        keep_pgids = {pid} if (pid := _mapping_stack_pid()) else None
        await _kill_stale_nvblox_processes(keep_pgids=keep_pgids)
        clock = await _probe_clock_monotonic()
        if not clock.ok:
            logger.warning(
                "Simulation /clock is not monotonic before nvblox start: %s",
                clock.to_dict(),
            )
        broadcasters = await _probe_tf_broadcasters()
        if not broadcasters.ok:
            logger.error(
                "TF broadcaster check failed before nvblox start: %s",
                broadcasters.to_dict(),
            )
        tf = await _wait_for_tf_stable(timeout_s=_setting_float("warehouse_preflight_tf_wait_s", 10.0))
        if not tf.ok:
            logger.warning(
                "TF not stable before nvblox start (continuing degraded): %s",
                tf.to_dict(),
            )
        from backend.modules.warehouse.service.sim_time_tf_readiness import (
            wait_for_warehouse_map_tf_stable,
        )

        map_tf = await wait_for_warehouse_map_tf_stable(timeout_s=3.0)
        if not map_tf.ok:
            logger.warning(
                "warehouse_map->odom TF not stable before nvblox start: %s",
                map_tf.to_dict(),
            )

    async with deps.resolve("_mapping_stack_lock"):
        if _is_mapping_stack_process_running():
            return

        from backend.infrastructure.warehouse.bridge_config import (
            list_ros2_topics_with_retry_async,
            preflight_core_ros_topics,
            ros_command_env,
        )
        from backend.modules.warehouse.service.live_map_bridge import _ros2_workspace

        ws = _ros2_workspace()
        core_required = preflight_core_ros_topics(ws)
        topics = await list_ros2_topics_with_retry_async(
            ws,
            attempts=6,
            pause_s=2.0,
            required_topics=core_required,
        )
        if not core_required.issubset(topics):
            missing = sorted(core_required - topics)
            logger.warning(
                "Starting Nvblox before warehouse bridge core topics are ready; "
                "missing=%s. Ensure warehouse_bridge.launch.py is running.",
                missing,
            )

        cmd = _build_nvblox_launch_command()

        logger.info("Starting Nvblox mapping stack: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=PIPE,
                stderr=PIPE,
                start_new_session=True,
                env=ros_command_env(),
            )

            deps.set_state("_mapping_stack_process", process)
            deps.set_state("_mapping_stack_started_at", datetime.now(UTC).isoformat())
            deps.set_state("_mapping_stack_last_exit_code", None)
            deps.set_state("_mapping_stack_last_error", None)
            deps.set_state("_last_nvblox_restart_at", time.monotonic())

            from backend.modules.warehouse.service.nvblox_status import (
                nvblox_status_tracker,
            )

            nvblox_log_parser = _get_nvblox_log_parser()
            nvblox_log_parser.note_restart()
            nvblox_status_tracker.reset_tf_counters()
            _note_mapping_startup("nvblox_start_monotonic")

            from .process_watch import _log_process_stream, _watch_mapping_stack_process

            _track_background_task(asyncio.create_task(
                _log_process_stream(process.stdout, prefix="nvblox:stdout")
            ))
            _track_background_task(asyncio.create_task(
                _log_process_stream(process.stderr, prefix="nvblox:stderr")
            ))
            _track_background_task(asyncio.create_task(_watch_mapping_stack_process(process)))

        except Exception as exc:
            deps.set_state("_mapping_stack_process", None)
            deps.set_state("_mapping_stack_last_error", str(exc))

            logger.exception("Failed to start Nvblox mapping stack.")
            raise RuntimeError(
                f"Failed to start Nvblox mapping stack: {exc}"
            ) from exc

    boot_grace_s = _setting_float("warehouse_nvblox_boot_grace_s", 2.0)
    await asyncio.sleep(max(0.0, boot_grace_s))

    process = deps.resolve("_mapping_stack_process")
    if process is not None and process.returncode is not None:
        deps.set_state("_mapping_stack_last_exit_code", process.returncode)
        raise RuntimeError(
            "Nvblox mapping stack exited immediately "
            f"with code {process.returncode}."
        )


__all__ = ["_maybe_start_mapping_stack_cmd"]
