from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.infrastructure.runtime.blocking import blocking_process_runner
from backend.infrastructure.warehouse.bridge_config.ros_env import ros_command_env


_PUBLISHER_COUNT_SCRIPT = """
import json, sys, time
import rclpy
from rclpy.node import Node

rclpy.init()
node = Node("warehouse_publisher_probe")
topics = json.loads(sys.argv[1])
deadline = time.monotonic() + 3.0
counts = {}
while True:
    counts = {topic: len(node.get_publishers_info_by_topic(topic)) for topic in topics}
    if all(count > 0 for count in counts.values()) or time.monotonic() >= deadline:
        break
    time.sleep(0.2)
print(json.dumps(counts))
node.destroy_node()
rclpy.shutdown()
"""


def count_topic_publishers(
    ros2_ws: Path,
    topics: set[str],
    *,
    timeout_s: float = 8.0,
) -> dict[str, int]:
    """Return publisher counts for all topics with one ROS subprocess.

    ``ros2 topic list`` can show topics created by subscribers, so preflight
    must verify publishers. Doing one ``ros2 topic info`` per topic was slow
    enough to make readiness time out; this rclpy probe performs one DDS
    discovery pass and returns all counts.
    """
    if not topics:
        return {}
    ws = ros2_ws.resolve()
    setup = ws / "install" / "setup.bash"
    if not setup.exists():
        return {}
    cmd = (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {setup} && "
        'python3 -c "$PROBE_SCRIPT" "$PROBE_TOPICS"'
    )
    env = ros_command_env()
    env["PROBE_SCRIPT"] = _PUBLISHER_COUNT_SCRIPT
    env["PROBE_TOPICS"] = json.dumps(sorted(topics))
    try:
        result = blocking_process_runner.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            return {}
        return {
            str(topic): int(count)
            for topic, count in parsed.items()
            if isinstance(count, int)
        }
    return {}
