from __future__ import annotations

import asyncio
import logging
import os
import shlex
import signal
import time
from asyncio.subprocess import PIPE
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from backend.core.config.runtime import settings
from backend.modules.warehouse.ports import WarehousePerceptionCommandResult
from backend.modules.warehouse.service.readiness_result import (
    WarehouseReadinessResult,
    readiness_for_takeoff,
    readiness_from_perception_status_strict,
)
from backend.observability.instruments import observed_span, structured_error

if TYPE_CHECKING:
    from backend.modules.warehouse.service.live_map_readiness import MappingReadinessResult

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
    tf_degraded: bool = False
    nvblox_health: dict[str, object] = field(default_factory=dict)


_mapping_stack_process: asyncio.subprocess.Process | None = None
_mapping_stack_started_at: str | None = None
_mapping_stack_last_exit_code: int | None = None
_mapping_stack_last_error: str | None = None
_mapping_stack_lock = asyncio.Lock()
_last_nvblox_restart_at: float = 0.0
_restart_in_progress = False
_warned_missing_startup_timing = False
_background_tasks: set[asyncio.Task[Any]] = set()


def _track_background_task(task: asyncio.Task[Any]) -> asyncio.Task[Any]:
    _background_tasks.add(task)

    def _cleanup(done: asyncio.Task[Any]) -> None:
        _background_tasks.discard(done)
        if done.cancelled():
            return
        try:
            done.exception()
        except Exception:
            logger.exception("background mapping-stack task failed")

    task.add_done_callback(_cleanup)
    return task


def _setting_float(name: str, default: float) -> float:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _setting_int(name: str, default: int) -> int:
    try:
        return max(0, int(getattr(settings, name, default)))
    except (TypeError, ValueError):
        return default


class _OptionalProbeResult:
    def __init__(self, *, ok: bool = True, detail: str = "optional helper unavailable") -> None:
        self.ok = ok
        self.detail = detail

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "detail": self.detail}


class _FallbackNvbloxLogParser:
    tf_jump_back_count = 0
    tf_old_data_count = 0

    def ingest(self, line: str) -> tuple[int, bool]:
        lowered = line.lower()
        if "error" in lowered or "exception" in lowered:
            return logging.ERROR, True
        if "warn" in lowered or "tf_old_data" in lowered or "jump back" in lowered:
            if "tf_old_data" in lowered:
                self.tf_old_data_count += 1
            if "jump back" in lowered:
                self.tf_jump_back_count += 1
            return logging.WARNING, True
        if (
            "started up nvblox node" in lowered
            or "resizing gpu hash capacity" in lowered
            or "exited" in lowered
        ):
            return logging.INFO, True
        return logging.DEBUG, False

    def should_restart_for_tf_instability(
        self,
        *,
        jump_threshold: int,
        cooldown_s: float,
        last_restart_at: float,
    ) -> bool:
        if self.tf_jump_back_count < max(1, int(jump_threshold)):
            return False
        return time.monotonic() - last_restart_at >= max(0.0, float(cooldown_s))

    def note_restart(self) -> None:
        self.tf_jump_back_count = 0
        self.tf_old_data_count = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "available": False,
            "warning": "nvblox_log_parser module unavailable; using inline fallback parser",
            "tf_jump_back_count": self.tf_jump_back_count,
            "tf_old_data_count": self.tf_old_data_count,
        }


_fallback_nvblox_log_parser: _FallbackNvbloxLogParser | None = None


def _get_nvblox_log_parser():
    global _fallback_nvblox_log_parser
    try:
        from backend.modules.warehouse.service.nvblox_log_parser import nvblox_log_parser

        return nvblox_log_parser
    except ModuleNotFoundError as exc:
        if _fallback_nvblox_log_parser is None:
            logger.warning("Optional nvblox log parser unavailable: %s", exc)
            _fallback_nvblox_log_parser = _FallbackNvbloxLogParser()
        return _fallback_nvblox_log_parser


def _note_mapping_startup(mark: str) -> None:
    global _warned_missing_startup_timing
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            note_mapping_startup,
        )

        note_mapping_startup(mark)
    except ModuleNotFoundError as exc:
        if not _warned_missing_startup_timing:
            logger.warning("Optional mapping startup timing unavailable: %s", exc)
            _warned_missing_startup_timing = True


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
                "use_lidar:=false "
                "use_rgbd:=true"
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

def _log_nvblox_line(prefix: str, line: str) -> None:
    nvblox_log_parser = _get_nvblox_log_parser()
    level, emit = nvblox_log_parser.ingest(line)
    if not emit:
        if nvblox_log_parser.should_restart_for_tf_instability(
            jump_threshold=_setting_int("warehouse_nvblox_tf_restart_jump_threshold", 3),
            cooldown_s=_setting_float("warehouse_nvblox_tf_restart_cooldown_s", 30.0),
            last_restart_at=_last_nvblox_restart_at,
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
    global _last_nvblox_restart_at
    global _restart_in_progress

    if _restart_in_progress:
        return

    nvblox_log_parser = _get_nvblox_log_parser()
    _restart_in_progress = True
    try:
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
        _last_nvblox_restart_at = time.monotonic()
        await _maybe_start_mapping_stack_cmd(skip_stale_kill=True)
    except Exception:
        logger.exception("Failed to restart nvblox after TF instability")
    finally:
        _restart_in_progress = False


async def _watch_mapping_stack_process(
        process: asyncio.subprocess.Process,
) -> None:
    global _mapping_stack_last_exit_code
    global _mapping_stack_last_error

    exit_code = await process.wait()

    if _mapping_stack_process is process:
        _mapping_stack_last_exit_code = exit_code

        if exit_code in (0, -signal.SIGTERM, signal.SIGTERM, 143):
            logger.info(
                "Nvblox mapping stack process exited normally with code %s.",
                exit_code,
            )
        else:
            if not _mapping_stack_last_error:
                _mapping_stack_last_error = (
                    f"Nvblox mapping stack exited with code {exit_code}."
                )
            logger.warning(
                "Nvblox mapping stack process exited with code %s.",
                exit_code,
            )
            _track_background_task(asyncio.create_task(_kill_stale_nvblox_processes()))


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
    global _mapping_stack_process
    global _mapping_stack_started_at
    global _mapping_stack_last_exit_code
    global _mapping_stack_last_error
    global _last_nvblox_restart_at

    # Reuse a warm, healthy stack instead of killing + restarting it.
    # The preflight warm-up already started nvblox; restarting here would
    # SIGTERM the warm process and pay the full re-warm (~25-30s) again on the
    # pre-takeoff critical path.
    if _is_mapping_stack_process_running():
        logger.info(
            "Nvblox mapping stack already running (pid=%s); reusing warm stack.",
            _mapping_stack_pid(),
        )
        return

    if not skip_stale_kill:
        # Never reap our own tracked stack (it runs in its own session/pgid).
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

    async with _mapping_stack_lock:
        if _is_mapping_stack_process_running():
            return

        from backend.infrastructure.warehouse.bridge_config import (
            list_ros2_topics_with_retry,
            preflight_core_ros_topics,
            ros_command_env,
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
                env=ros_command_env(),
            )

            _mapping_stack_process = process
            _mapping_stack_started_at = datetime.now(UTC).isoformat()
            _mapping_stack_last_exit_code = None
            _mapping_stack_last_error = None
            _last_nvblox_restart_at = time.monotonic()

            from backend.modules.warehouse.service.nvblox_status import (
                nvblox_status_tracker,
            )

            nvblox_log_parser = _get_nvblox_log_parser()
            nvblox_log_parser.note_restart()
            nvblox_status_tracker.reset_tf_counters()
            _note_mapping_startup("nvblox_start_monotonic")

            _track_background_task(asyncio.create_task(
                _log_process_stream(process.stdout, prefix="nvblox:stdout")
            ))
            _track_background_task(asyncio.create_task(
                _log_process_stream(process.stderr, prefix="nvblox:stderr")
            ))
            _track_background_task(asyncio.create_task(_watch_mapping_stack_process(process)))

        except Exception as exc:
            _mapping_stack_process = None
            _mapping_stack_last_error = str(exc)

            logger.exception("Failed to start Nvblox mapping stack.")
            raise RuntimeError(
                f"Failed to start Nvblox mapping stack: {exc}"
            ) from exc

    boot_grace_s = _setting_float("warehouse_nvblox_boot_grace_s", 2.0)
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
    try:
        return await _get_mapping_stack_status_impl()
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
            started_at=_mapping_stack_started_at,
            last_exit_code=_mapping_stack_last_exit_code,
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

    status = await fetch_warehouse_perception_status(deep=True, force=False)
    flight_readiness = readiness_from_perception_status_strict(status)
    bridge = live_map_bridge_status()

    process_running = _is_mapping_stack_process_running()

    from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker

    nvblox_log_parser = _get_nvblox_log_parser()
    nvblox_status_tracker.note_process_running(process_running)
    if _mapping_stack_last_error and not process_running:
        nvblox_status_tracker.note_error(_mapping_stack_last_error)

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
        last_error = status.detail or _mapping_stack_last_error
    elif _mapping_stack_last_error and not flight_readiness.nvblox_ready:
        last_error = _mapping_stack_last_error

    nvblox_running = bool(flight_readiness.nvblox_ready and not tf_degraded)

    return WarehouseMappingStackStatus(
        running=running,
        pid=_mapping_stack_pid(),
        started_at=_mapping_stack_started_at,
        last_exit_code=_mapping_stack_last_exit_code,
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


async def prepare_warehouse_scan_ros(
        *,
        require_nvblox: bool,
        sensor_timeout_s: float,
        nvblox_timeout_s: float,
        wait_for_rgbd: bool = True,
) -> tuple[
    WarehouseMappingStackStatus,
    WarehouseReadinessResult,
    WarehouseReadinessResult,
    MappingReadinessResult,
]:
    from backend.modules.warehouse.service.live_map_readiness import (
        MappingReadinessResult,
        peek_cached_rgbd_readiness,
        wait_for_rgbd_mapping_topics,
    )
    from backend.modules.warehouse.service.warehouse_preflight import (
        fetch_warehouse_perception_status,
    )

    await _maybe_start_mapping_stack_cmd()

    status = await fetch_warehouse_perception_status(deep=True, force=True)
    takeoff_ready = readiness_for_takeoff(status)
    flight_readiness = readiness_from_perception_status_strict(status)

    if wait_for_rgbd and sensor_timeout_s > 0:
        cached_rgbd = peek_cached_rgbd_readiness()
        if cached_rgbd is not None and cached_rgbd.ready:
            rgbd_readiness = cached_rgbd
            logger.info(
                "Reusing pre-warmed RGB-D readiness (topic=%r nvblox_pointclouds=%s)",
                rgbd_readiness.rgbd_pointcloud_topic,
                rgbd_readiness.nvblox_pointcloud_topics,
            )
        else:
            rgbd_readiness = await wait_for_rgbd_mapping_topics(timeout_s=sensor_timeout_s)
        if not rgbd_readiness.ready:
            logger.warning(
                "RGB-D mapping topics not fully ready after %.1fs; missing=%s warnings=%s",
                sensor_timeout_s,
                rgbd_readiness.missing_topics,
                rgbd_readiness.warnings,
            )
        else:
            flags = rgbd_readiness.readiness_flags()
            if flags["rgbd_colored_pointcloud_ready"]:
                logger.info(
                    "RGB-D PointCloud2 stream ready for warehouse scan "
                    "(topic=%r nvblox_pointclouds=%s)",
                    rgbd_readiness.rgbd_pointcloud_topic,
                    rgbd_readiness.nvblox_pointcloud_topics,
                )
            elif flags["rgbd_input_ready"]:
                logger.info(
                    "RGB-D camera inputs ready for nvblox integration "
                    "(inputs_ready=%s nvblox_pointclouds=%s)",
                    rgbd_readiness.rgbd_input_topics_ready,
                    rgbd_readiness.nvblox_pointcloud_topics,
                )
            else:
                logger.info(
                    "RGB-D mapping readiness satisfied with partial inputs (%s)",
                    rgbd_readiness.to_dict(),
                )
    else:
        rgbd_readiness = MappingReadinessResult(
            ready=False,
            warnings=["RGB-D warmup deferred until after takeoff"],
        )
        logger.info(
            "Skipping RGB-D readiness wait before takeoff (wait_for_rgbd=%s timeout=%.1fs)",
            wait_for_rgbd,
            sensor_timeout_s,
        )

    deadline = asyncio.get_running_loop().time() + max(0.0, nvblox_timeout_s)
    flight_readiness = _merge_nvblox_readiness_from_rgbd(flight_readiness, rgbd_readiness)

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

        status = await fetch_warehouse_perception_status(
            deep=True, force=True, bypass_cache=True
        )
        takeoff_ready = readiness_for_takeoff(status)
        flight_readiness = readiness_from_perception_status_strict(status)
        flight_readiness = _merge_nvblox_readiness_from_rgbd(flight_readiness, rgbd_readiness)

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

    return stack_status, flight_readiness, takeoff_ready, rgbd_readiness


async def _stop_mapping_stack_process(*, strict: bool = False) -> bool:
    """
    Stop the Nvblox mapping stack process.

    Returns:
        True  -> process was stopped or already gone
        False -> cleanup had a non-fatal problem

    strict=True can be used in tests/admin commands if you want cleanup errors
    to fail loudly. Mission shutdown should normally use strict=False.
    """
    global _mapping_stack_process

    async with _mapping_stack_lock:
        process = _mapping_stack_process
    if process is None:
        return True

    pid = getattr(process, "pid", None)

    try:
        if process.returncode is not None:
            logger.info("Nvblox mapping stack already stopped pid=%s", pid)
            async with _mapping_stack_lock:
                if _mapping_stack_process is process:
                    _mapping_stack_process = None
            return True

        logger.info("Stopping Nvblox mapping stack process pid=%s", pid)

        # Try graceful process-group termination first.
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            logger.info("Nvblox process group already gone pid=%s", pid)
            async with _mapping_stack_lock:
                if _mapping_stack_process is process:
                    _mapping_stack_process = None
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

        # Wait for graceful shutdown.
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
        # Always clear the stored handle so stale process objects do not poison
        # the next warehouse scan.
        async with _mapping_stack_lock:
            if _mapping_stack_process is process:
                _mapping_stack_process = None


async def shutdown_warehouse_mapping_stack() -> None:
    from backend.modules.warehouse.service.live_map_bridge import (
        stop_warehouse_live_map_bridge,
    )

    with observed_span(
        "mapping.stack.stop",
        ros_topic="/warehouse/front/rgbd/points",
        **{"mapping.layer": "nvblox"},
    ):
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

    if _background_tasks:
        for task in tuple(_background_tasks):
            task.cancel()
        await asyncio.gather(*tuple(_background_tasks), return_exceptions=True)

    shutdown_cmd = str(getattr(settings, "warehouse_shutdown_mapping_stack_cmd", "") or "").strip()
    if shutdown_cmd:
        try:
            await asyncio.to_thread(
                __import__("subprocess").run,
                shutdown_cmd,
                shell=True,
                check=False,
                timeout=10,
            )
        except Exception:
            logger.warning("Non-fatal error while running mapping shutdown command", exc_info=True)
