"""Warehouse live-map readiness — ros commands."""

from __future__ import annotations


import logging
import shlex
import subprocess
from pathlib import Path

from backend.infrastructure.runtime.blocking import blocking_process_runner
from backend.modules.warehouse.service.map_source_config import RGBD_INPUT_TOPICS

from . import deps

logger = logging.getLogger(__name__)
def _ros2_workspace() -> Path:
    from backend.modules.warehouse.service.runtime_settings import ros2_workspace

    return ros2_workspace()

def _source_setup(ws: Path) -> str:
    return (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {shlex.quote(str(ws / 'install/setup.bash'))}"
    )

def _run_sourced_ros_command(command: str, *, ws: Path, timeout_s: float) -> subprocess.CompletedProcess[str] | None:
    cmd = f"{_source_setup(ws)} && {command}"
    try:
        return blocking_process_runner.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=max(0.5, timeout_s),
            check=False,
            env=deps.resolve("ros_command_env")(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

def _topic_info(topic: str, ws: Path) -> str | None:
    result = _run_sourced_ros_command(
        f"timeout 3 ros2 topic info {shlex.quote(topic)} -v",
        ws=ws,
        timeout_s=5.0,
    )
    if result is None or result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "Type:" in line:
            return line.split("Type:", 1)[1].strip()
    return None

def _topic_message_text(topic: str, ws: Path, *, timeout_s: float = 3.0) -> str | None:
    """Check that at least one message arrives on topic (no hz averaging)."""
    bounded_timeout = max(0.5, float(timeout_s))
    result = _run_sourced_ros_command(
        f"timeout {max(0.5, bounded_timeout):.3f} ros2 topic echo {shlex.quote(topic)} --once",
        ws=ws,
        timeout_s=bounded_timeout + 1.0,
    )
    if result is None or result.returncode != 0:
        return None
    output = (result.stdout or "").strip()
    return output or None

def _topic_has_message(topic: str, ws: Path, *, timeout_s: float = 3.0) -> bool:
    return _topic_message_text(topic, ws, timeout_s=timeout_s) is not None

def _valid_esdf_message(output: str) -> bool:
    lowered = output.lower()
    return bool(
        "frame_id:" in lowered
        and all(f"name: {field}" in lowered for field in ("x", "y", "z"))
    )

def _valid_occupancy_message(output: str) -> bool:
    lowered = output.lower()
    return bool("frame_id:" in lowered and "width:" in lowered and "height:" in lowered)
