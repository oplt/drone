from __future__ import annotations

import subprocess
from pathlib import Path

from backend.infrastructure.warehouse.bridge_config.publisher_probe import count_topic_publishers
from backend.infrastructure.warehouse.bridge_config.topic_list import (
    list_ros2_topics_with_retry,
    preflight_core_ros_topics,
)
from backend.infrastructure.runtime.blocking import run_blocking


def quick_ros_bridge_check(ros2_ws: Path) -> tuple[bool | None, str]:
    """Lightweight bridge-up check used before starting the bridge process."""
    ws = ros2_ws.resolve()
    setup = ws / "install" / "setup.bash"
    if not setup.exists():
        return False, f"ROS 2 workspace is not built: {setup}"
    try:
        core_required = preflight_core_ros_topics(ws)
        topics = list_ros2_topics_with_retry(
            ws,
            attempts=2,
            pause_s=1.0,
            required_topics=core_required,
        )
        publisher_counts = count_topic_publishers(ws, core_required | {"/clock"})
    except FileNotFoundError:
        return False, "bash is not available; cannot probe ROS 2."
    except subprocess.TimeoutExpired:
        return None, "ROS 2 topic probe timed out."
    except RuntimeError as exc:
        return False, str(exc)
    if core_required.issubset(topics) and all(
        publisher_counts.get(topic, 0) > 0 for topic in core_required
    ):
        return True, f"ROS bridge core topics are present ({len(core_required)} required)."

    missing_core = sorted(core_required - topics)
    warehouse_topics = [topic for topic in topics if topic.startswith("/warehouse/")]
    if warehouse_topics:
        preview = ", ".join(missing_core[:4])
        suffix = "…" if len(missing_core) > 4 else ""
        return (
            None,
            "ROS graph has partial warehouse topics, but bridge core topics are "
            f"still missing: {preview}{suffix}. Start warehouse_bridge.launch.py.",
        )
    return None, "ROS graph reachable, but no /warehouse topics are publishing yet."


async def quick_ros_bridge_check_async(ros2_ws: Path) -> tuple[bool | None, str]:
    """Event-loop-safe bridge readiness adapter."""
    return await run_blocking(
        quick_ros_bridge_check,
        ros2_ws,
        boundary="process",
        operation="ros_bridge_probe",
        call_timeout_s=30.0,
    )
