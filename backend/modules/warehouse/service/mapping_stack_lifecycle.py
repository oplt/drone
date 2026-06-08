from __future__ import annotations

import asyncio
import logging
import shlex
import signal
from asyncio.subprocess import PIPE
from dataclasses import dataclass
from datetime import datetime, timezone
from backend.core.config.runtime import settings

from backend.modules.warehouse.ports import WarehousePerceptionCommandResult
from backend.modules.warehouse.service.readiness_result import (
    WarehouseReadinessResult,
    readiness_for_takeoff,
    readiness_from_perception_status_strict,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WarehouseMappingStackStatus:
    running: bool
    pid: int | None = None
    started_at: str | None = None
    last_exit_code: int | None = None
    last_error: str | None = None
    nvblox_running: bool = False
    phase: str = "stopped"


_mapping_stack_process: asyncio.subprocess.Process | None = None
_mapping_stack_started_at: str | None = None
_mapping_stack_last_exit_code: int | None = None
_mapping_stack_last_error: str | None = None
_mapping_stack_lock = asyncio.Lock()


def mapping_stack_not_running_result() -> WarehousePerceptionCommandResult:
    return WarehousePerceptionCommandResult(
        accepted=False,
        status="mapping_stack_not_running",
        detail="Warehouse mapping stack is not running.",
    )


def _is_mapping_stack_process_running() -> bool:
    return (
            _mapping_stack_process is not None
            and _mapping_stack_process.returncode is None
    )


def _mapping_stack_pid() -> int | None:
    if _mapping_stack_process is None:
        return None
    return _mapping_stack_process.pid


def _build_nvblox_launch_command() -> list[str]:
    ros_distro = (settings.ROS_DISTRO or "jazzy").strip()

    ros_setup_file = (
            settings.WAREHOUSE_ROS_SETUP_FILE
            or f"/opt/ros/{ros_distro}/setup.bash"
    ).strip()

    workspace_setup_file = (
            settings.WAREHOUSE_ROS_WORKSPACE_SETUP_FILE or ""
    ).strip()

    launch_package = (
            settings.WAREHOUSE_NVBLOX_LAUNCH_PACKAGE
            or "drone_gz_bridge"
    ).strip()

    launch_file = (
            settings.WAREHOUSE_NVBLOX_LAUNCH_FILE
            or "warehouse_nvblox.launch.py"
    ).strip()

    launch_args_raw = (
            settings.WAREHOUSE_NVBLOX_LAUNCH_ARGS
            or (
                "use_sim_time:=true "
                "run_rviz:=false "
                "start_odom_to_tf:=false "
                "start_odom_to_pose:=false "
                "use_tf_transforms:=true "
                "use_topic_transforms:=false "
                "input_qos:=SENSOR_DATA "
                "global_frame:=odom "
                "pose_frame:=iris_with_standoffs/base_link "
                "use_lidar:=true"
            )
    ).strip()

    launch_args = shlex.split(launch_args_raw)

    if not launch_package:
        raise RuntimeError("WAREHOUSE_NVBLOX_LAUNCH_PACKAGE is empty.")

    if not launch_file:
        raise RuntimeError("WAREHOUSE_NVBLOX_LAUNCH_FILE is empty.")

    ros2_launch_cmd = [
        "ros2",
        "launch",
        launch_package,
        launch_file,
        *launch_args,
    ]

    script_parts: list[str] = []

    if ros_setup_file:
        script_parts.append(f"source {shlex.quote(ros_setup_file)}")

    if workspace_setup_file:
        script_parts.append(f"source {shlex.quote(workspace_setup_file)}")

    script_parts.append(
        "exec " + " ".join(shlex.quote(part) for part in ros2_launch_cmd)
    )

    return ["bash", "-lc", " && ".join(script_parts)]

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

        logger.info(
            "[%s] %s",
            prefix,
            line.decode(errors="replace").rstrip(),
        )


async def _watch_mapping_stack_process(
        process: asyncio.subprocess.Process,
) -> None:
    global _mapping_stack_last_exit_code
    global _mapping_stack_last_error

    exit_code = await process.wait()

    if _mapping_stack_process is process:
        _mapping_stack_last_exit_code = exit_code

        if exit_code != 0 and not _mapping_stack_last_error:
            _mapping_stack_last_error = (
                f"Nvblox mapping stack exited with code {exit_code}."
            )

        logger.warning(
            "Nvblox mapping stack process exited with code %s.",
            exit_code,
        )


async def _maybe_start_mapping_stack_cmd() -> None:
    """
    Start the Nvblox mapping stack through ROS 2 launch.

    This function intentionally keeps the old name because
    prepare_warehouse_scan_ros() already calls it.

    Important:
        Do not use subprocess.run(..., timeout=30) for Nvblox.
        Nvblox is a long-running ROS process. If it starts correctly,
        it should stay alive until shutdown.
    """
    global _mapping_stack_process
    global _mapping_stack_started_at
    global _mapping_stack_last_exit_code
    global _mapping_stack_last_error

    async with _mapping_stack_lock:
        if _is_mapping_stack_process_running():
            return

        from backend.infrastructure.warehouse.bridge_config import (
            list_ros2_topics_with_retry,
            preflight_core_ros_topics,
        )
        from backend.modules.warehouse.service.live_map_bridge import _ros2_workspace

        ws = _ros2_workspace()
        core_required = preflight_core_ros_topics(ws)
        topics = await asyncio.to_thread(
            list_ros2_topics_with_retry,
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
            )

            _mapping_stack_process = process
            _mapping_stack_started_at = datetime.now(timezone.utc).isoformat()
            _mapping_stack_last_exit_code = None
            _mapping_stack_last_error = None

            asyncio.create_task(
                _log_process_stream(
                    process.stdout,
                    prefix="nvblox:stdout",
                )
            )

            asyncio.create_task(
                _log_process_stream(
                    process.stderr,
                    prefix="nvblox:stderr",
                )
            )

            asyncio.create_task(_watch_mapping_stack_process(process))

        except Exception as exc:
            _mapping_stack_process = None
            _mapping_stack_last_error = str(exc)

            logger.exception("Failed to start Nvblox mapping stack.")
            raise RuntimeError(
                f"Failed to start Nvblox mapping stack: {exc}"
            ) from exc

    boot_grace_s = settings.warehouse_nvblox_boot_grace_s
    await asyncio.sleep(max(0.0, boot_grace_s))

    if (
            _mapping_stack_process is not None
            and _mapping_stack_process.returncode is not None
    ):
        _mapping_stack_last_exit_code = _mapping_stack_process.returncode
        raise RuntimeError(
            "Nvblox mapping stack exited immediately "
            f"with code {_mapping_stack_last_exit_code}."
        )


async def get_mapping_stack_status() -> WarehouseMappingStackStatus:
    from backend.modules.warehouse.service.live_map_bridge import (
        live_map_bridge_status,
    )
    from backend.modules.warehouse.service.warehouse_preflight import (
        fetch_warehouse_perception_status,
    )

    status = await fetch_warehouse_perception_status(deep=True, force=False)
    flight_readiness = readiness_from_perception_status_strict(status)
    bridge = live_map_bridge_status()

    process_running = _is_mapping_stack_process_running()

    running = bool(
        process_running
        or status.reachable
        or status.configured
        or bridge.get("running")
        or flight_readiness.core_ready
    )

    if flight_readiness.nvblox_ready:
        phase = "ready"
    elif running:
        phase = "starting"
    else:
        phase = "stopped"

    last_error = None
    if not running:
        last_error = status.detail or _mapping_stack_last_error
    elif _mapping_stack_last_error and not flight_readiness.nvblox_ready:
        last_error = _mapping_stack_last_error

    return WarehouseMappingStackStatus(
        running=running,
        pid=_mapping_stack_pid(),
        started_at=_mapping_stack_started_at,
        last_exit_code=_mapping_stack_last_exit_code,
        last_error=last_error,
        nvblox_running=flight_readiness.nvblox_ready,
        phase=phase,
    )


async def prepare_warehouse_scan_ros(
        *,
        require_nvblox: bool,
        sensor_timeout_s: float,
        nvblox_timeout_s: float,
) -> tuple[
    WarehouseMappingStackStatus,
    WarehouseReadinessResult,
    WarehouseReadinessResult,
]:
    del sensor_timeout_s

    from backend.modules.warehouse.service.warehouse_preflight import (
        fetch_warehouse_perception_status,
    )

    await _maybe_start_mapping_stack_cmd()

    deadline = asyncio.get_running_loop().time() + max(0.0, nvblox_timeout_s)

    status = await fetch_warehouse_perception_status(deep=True, force=True)
    takeoff_ready = readiness_for_takeoff(status)
    flight_readiness = readiness_from_perception_status_strict(status)

    while require_nvblox and not flight_readiness.nvblox_ready:
        if asyncio.get_running_loop().time() >= deadline:
            flight_readiness = WarehouseReadinessResult(
                **{
                    **flight_readiness.to_dict(),
                    "ready": False,
                    "detail": flight_readiness.detail
                              or "Nvblox is not publishing a ready ESDF/costmap signal.",
                }
            )
            break

        await asyncio.sleep(1.0)

        status = await fetch_warehouse_perception_status(deep=True, force=True)
        takeoff_ready = readiness_for_takeoff(status)
        flight_readiness = readiness_from_perception_status_strict(status)

    process_running = _is_mapping_stack_process_running()

    running = bool(
        process_running
        or status.reachable
        or status.configured
        or takeoff_ready.core_ready
    )

    if flight_readiness.nvblox_ready:
        phase = "ready"
    elif running:
        phase = "starting"
    else:
        phase = "stopped"

    stack_status = WarehouseMappingStackStatus(
        running=running,
        pid=_mapping_stack_pid(),
        started_at=_mapping_stack_started_at,
        last_exit_code=_mapping_stack_last_exit_code,
        last_error=None if takeoff_ready.core_ready else (
                takeoff_ready.detail or _mapping_stack_last_error
        ),
        nvblox_running=flight_readiness.nvblox_ready,
        phase=phase,
    )

    return stack_status, flight_readiness, takeoff_ready


async def _stop_mapping_stack_process() -> None:
    global _mapping_stack_process
    global _mapping_stack_last_exit_code

    process = _mapping_stack_process

    if process is None:
        return

    if process.returncode is not None:
        _mapping_stack_last_exit_code = process.returncode
        return

    logger.info("Stopping Nvblox mapping stack process pid=%s.", process.pid)

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(process.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning(
            "Nvblox mapping stack did not stop after SIGTERM; sending SIGKILL."
        )

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        await process.wait()

    _mapping_stack_last_exit_code = process.returncode


async def shutdown_warehouse_mapping_stack() -> None:
    from backend.modules.warehouse.service.live_map_bridge import (
        stop_warehouse_live_map_bridge,
    )

    await stop_warehouse_live_map_bridge()
    await _stop_mapping_stack_process()

    shutdown_cmd = settings.warehouse_shutdown_mapping_stack_cmd.strip()
    if shutdown_cmd:
        await asyncio.to_thread(
            __import__("subprocess").run,
            shutdown_cmd,
            shell=True,
            check=False,
            timeout=10,
        )