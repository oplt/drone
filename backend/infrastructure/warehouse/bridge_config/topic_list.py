from __future__ import annotations

import random
import time
from pathlib import Path

from backend.core.config.runtime import settings
from backend.infrastructure.runtime.blocking import blocking_process_runner, run_blocking
from backend.infrastructure.warehouse.bridge_config.models import (
    BridgeTopicMapping,
    gz_to_ros_mappings,
    load_bridge_config,
)
from backend.infrastructure.warehouse.bridge_config.preflight_filters import (
    _preflight_imu,
    _preflight_odometry,
    _preflight_rgbd,
)
from backend.infrastructure.warehouse.bridge_config.ros_env import ros_command_env


def preflight_core_ros_topics(ros2_ws: Path) -> set[str]:
    """ROS topic names required before warehouse preflight can pass (from yaml)."""
    bridged = gz_to_ros_mappings(load_bridge_config(ros2_ws.resolve()))
    names: set[str] = set()
    for entry in (
        *_preflight_odometry(bridged),
        *_preflight_imu(bridged),
        *_preflight_rgbd(bridged),
    ):
        names.add(entry.ros_topic_name)
    return names


def list_ros2_topics_with_retry(
    ros2_ws: Path,
    *,
    attempts: int | None = None,
    pause_s: float | None = None,
    required_topics: set[str] | None = None,
) -> set[str]:
    """List ROS topics; retry until required topics appear or attempts exhaust."""
    if attempts is None:
        attempts = max(1, settings.warehouse_bridge_topic_probe_attempts)
    if pause_s is None:
        pause_s = settings.warehouse_bridge_topic_probe_pause_s

    ws = ros2_ws.resolve()
    last: set[str] = set()
    for attempt in range(attempts):
        try:
            last = list_ros2_topics(ws)
        except RuntimeError:
            last = set()
        if required_topics:
            ready = required_topics.issubset(last)
        else:
            ready = any(topic.startswith("/warehouse/") for topic in last)
        if ready:
            return last
        if attempt + 1 < attempts:
            retry_pause = max(0.2, pause_s) * random.uniform(0.8, 1.2)
            time.sleep(retry_pause)
    return last


async def list_ros2_topics_async(ros2_ws: Path) -> set[str]:
    """Event-loop-safe ROS topic listing adapter."""
    return await run_blocking(
        list_ros2_topics,
        ros2_ws,
        boundary="process",
        operation="ros_topic_list",
        call_timeout_s=10.0,
    )


async def list_ros2_topics_with_retry_async(
    ros2_ws: Path,
    *,
    attempts: int | None = None,
    pause_s: float | None = None,
    required_topics: set[str] | None = None,
) -> set[str]:
    """Async adapter for topic discovery/retry polling."""
    return await run_blocking(
        list_ros2_topics_with_retry,
        ros2_ws,
        attempts=attempts,
        pause_s=pause_s,
        required_topics=required_topics,
        boundary="process",
        operation="ros_topic_probe_retry",
        call_timeout_s=30.0,
    )


def list_ros2_topics(ros2_ws: Path) -> set[str]:
    ws = ros2_ws.resolve()
    setup = ws / "install" / "setup.bash"
    if not setup.exists():
        raise RuntimeError(f"ROS 2 workspace is not built: {setup}")
    cmd = (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {setup} && "
        "ros2 topic list --no-daemon"
    )
    result = blocking_process_runner.run(
        ["bash", "-lc", cmd],
        cwd=str(ws),
        capture_output=True,
        timeout=8,
        check=False,
        env=ros_command_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return {
        line.strip()
        for line in result.stdout.decode(errors="replace").splitlines()
        if line.strip()
    }
