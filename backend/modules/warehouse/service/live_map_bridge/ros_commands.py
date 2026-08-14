"""Warehouse live-map bridge — ROS CLI command helpers."""

from __future__ import annotations

import logging
import math
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path

from backend.infrastructure.warehouse.bridge_config import ros_command_env
from backend.infrastructure.runtime.blocking import blocking_process_runner

logger = logging.getLogger(__name__)


def _ros_setup_command(ws: Path) -> str:
    install_setup = ws / "install/setup.bash"
    return (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {shlex.quote(str(install_setup))}"
    )


def _run_ros2_command(
    *,
    ws: Path,
    ros_args: Iterable[str],
    shell_timeout_s: float,
    process_timeout_s: float,
) -> subprocess.CompletedProcess[str] | None:
    command = (
        f"{_ros_setup_command(ws)} && "
        f"timeout {shlex.quote(str(max(1, int(math.ceil(shell_timeout_s)))))} "
        f"ros2 {' '.join(shlex.quote(str(arg)) for arg in ros_args)}"
    )
    try:
        return blocking_process_runner.run(
            ["bash", "-lc", command],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=process_timeout_s,
            check=False,
            env=ros_command_env(),
        )
    except subprocess.TimeoutExpired:
        logger.debug("ROS command timed out: ros2 %s", " ".join(map(str, ros_args)))
        return None
    except OSError:
        logger.debug(
            "ROS command failed to start: ros2 %s", " ".join(map(str, ros_args)), exc_info=True
        )
        return None


def _list_ros2_topics_safe(ws: Path) -> set[str]:
    from backend.infrastructure.warehouse.bridge_config import list_ros2_topics

    try:
        return set(list_ros2_topics(ws))
    except RuntimeError:
        logger.debug("Could not list ROS2 topics", exc_info=True)
        return set()


__all__ = ["_list_ros2_topics_safe", "_run_ros2_command", "_ros_setup_command"]
