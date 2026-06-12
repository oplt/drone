from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.warehouse.bridge_config import ros_command_env


def _clock_stability_window_s() -> float:
    return float(getattr(settings, "warehouse_live_map_clock_stability_s", 4.0))


def _sourced_ros_cmd(inner: str) -> list[str]:
    """Wrap a ros2 CLI invocation in a shell that sources the ROS environment.

    The backend process is not started from a ROS-sourced shell and
    ``ros_command_env()`` strips PYTHONPATH, so invoking ``ros2`` directly
    always fails; every probe must source setup.bash first.
    """
    ws = Path(settings.warehouse_ros2_ws.strip() or "ros2_ws").expanduser().resolve()
    setup = ws / "install" / "setup.bash"
    source_ws = f"source {setup} && " if setup.exists() else ""
    return [
        "bash",
        "-lc",
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && " f"{source_ws}{inner}",
    ]


_CLOCK_PROBE_SCRIPT = """
import json, sys, time
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock

window_s = float(sys.argv[1])
samples = []

rclpy.init()
node = Node("warehouse_clock_probe")

def _on_clock(msg):
    value = float(msg.clock.sec) + float(msg.clock.nanosec) / 1_000_000_000.0
    if not samples or value - samples[-1] >= 0.1:
        samples.append(value)

qos = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
node.create_subscription(Clock, "/clock", _on_clock, qos)
deadline = time.monotonic() + max(0.5, window_s)
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)
    if len(samples) >= 2 and time.monotonic() + 0.2 >= deadline:
        break

print(json.dumps(samples))
node.destroy_node()
rclpy.shutdown()
"""


@dataclass
class SimTimeStatus:
    ok: bool
    detail: str
    jump_back_count: int = 0
    frozen_count: int = 0
    large_forward_jump_count: int = 0
    samples: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "detail": self.detail,
            "jump_back_count": self.jump_back_count,
            "frozen_count": self.frozen_count,
            "large_forward_jump_count": self.large_forward_jump_count,
            "samples": list(self.samples),
        }


def _parse_clock_time(stdout: str) -> float | None:
    sec: int | None = None
    nanosec = 0
    for raw in stdout.splitlines():
        line = raw.strip()
        if line.startswith("sec:"):
            try:
                sec = int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
        elif line.startswith("nanosec:"):
            try:
                nanosec = int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    if sec is None:
        return None
    return float(sec) + (float(nanosec) / 1_000_000_000.0)


async def _read_clock_once(timeout_s: float = 3.0) -> float | None:
    # The ros2 CLI takes >1s just to start up; shorter timeouts always
    # false-negative as "/clock missing" even when the clock is publishing.
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            _sourced_ros_cmd(
                f"timeout {max(2.0, timeout_s)} ros2 topic echo /clock --once"
            ),
            env=ros_command_env(),
            capture_output=True,
            text=True,
            timeout=max(4.5, timeout_s + 2.0),
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return _parse_clock_time(result.stdout)


async def probe_clock_monotonic(
    *,
    window_s: float | None = None,
    poll_s: float = 0.25,
    max_forward_jump_s: float = 2.0,
) -> SimTimeStatus:
    window = max(4.0, float(window_s if window_s is not None else _clock_stability_window_s()))
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            _sourced_ros_cmd('python3 -c "$CLOCK_PROBE_SCRIPT" "$CLOCK_WINDOW_S"'),
            env={
                **ros_command_env(),
                "CLOCK_PROBE_SCRIPT": _CLOCK_PROBE_SCRIPT,
                "CLOCK_WINDOW_S": str(max(0.5, window)),
            },
            capture_output=True,
            text=True,
            timeout=max(3.0, window + 3.0),
            check=False,
        )
        samples = json.loads((result.stdout or "[]").splitlines()[-1])
        if not isinstance(samples, list):
            samples = []
        samples = [float(sample) for sample in samples]
    except Exception:
        samples = []

    if not samples:
        return SimTimeStatus(False, "/clock missing or not publishing", samples=[])

    jumps = frozen = forward = 0
    previous: float | None = None
    for sample in samples:
        if previous is not None:
            delta = sample - previous
            if delta < -1e-6:
                jumps += 1
            elif abs(delta) <= 1e-9:
                frozen += 1
            elif delta > max_forward_jump_s:
                forward += 1
        previous = sample

    ok = bool(samples) and jumps == 0 and frozen < max(2, len(samples) // 2) and forward == 0
    detail = "clock monotonic" if ok else "clock unstable"
    return SimTimeStatus(ok, detail, jumps, frozen, forward, samples)


async def probe_tf_broadcasters() -> SimTimeStatus:
    return await wait_for_tf_stable(timeout_s=1.5)


async def wait_for_tf_stable(
    *,
    timeout_s: float,
    parent_frame: str = "odom",
    child_frame: str = "iris_with_standoffs/base_link",
) -> SimTimeStatus:
    deadline = time.monotonic() + max(0.1, timeout_s)
    last_detail = "tf lookup failed"
    while time.monotonic() < deadline:
        try:
            # tf2_echo needs ~2s to start, subscribe and print its first
            # lookup; a 1s timeout would fail even with a healthy TF tree.
            result = await asyncio.to_thread(
                subprocess.run,
                _sourced_ros_cmd(
                    f"timeout 3.0 ros2 run tf2_ros tf2_echo {parent_frame} {child_frame}"
                ),
                env=ros_command_env(),
                capture_output=True,
                text=True,
                timeout=5.5,
                check=False,
            )
            # tf2_echo spins forever and is killed by `timeout` (exit 124), so
            # success is determined by a printed lookup, not the exit code.
            if "At time" in (result.stdout or ""):
                return SimTimeStatus(True, "tf stable")
            last_detail = (result.stderr or result.stdout or "tf lookup failed")[:240]
        except Exception as exc:
            last_detail = str(exc)[:240]
        await asyncio.sleep(0.2)
    return SimTimeStatus(False, last_detail)


async def kill_stale_nvblox_processes() -> None:
    """Terminate orphaned Nvblox launch/container processes before restart.

    Stale component containers keep GPU allocations alive and are a direct
    contributor to the observed cudaMallocAsync out-of-memory crash.
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["ps", "-eo", "pid=,pgid=,command="],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
            env=ros_command_env(),
        )
    except Exception:
        return
    if result.returncode != 0:
        return

    current_pid = os.getpid()
    groups: set[int] = set()
    for raw in result.stdout.splitlines():
        parts = raw.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            pgid = int(parts[1])
        except ValueError:
            continue
        cmd = parts[2]
        if pid == current_pid:
            continue
        if (
            "warehouse_nvblox.launch.py" in cmd
            or "__node:=nvblox_container" in cmd
            or "[nvblox_node]" in cmd
        ):
            groups.add(pgid)

    for sig, delay in ((signal.SIGTERM, 0.8), (signal.SIGKILL, 0.0)):
        for pgid in list(groups):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                groups.discard(pgid)
            except PermissionError:
                groups.discard(pgid)
        if delay:
            await asyncio.sleep(delay)
