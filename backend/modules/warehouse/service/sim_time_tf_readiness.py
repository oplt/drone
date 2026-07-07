from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.warehouse.bridge_config import ros_command_env

logger = logging.getLogger(__name__)


def _safe_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _safe_float(value: object, default: float, *, min_value: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not math.isfinite(parsed):
        parsed = default
    if min_value is not None:
        parsed = max(min_value, parsed)
    return parsed


def _clock_stability_window_s() -> float:
    return _safe_float(
        getattr(settings, "warehouse_live_map_clock_stability_s", 4.0),
        4.0,
        min_value=0.5,
    )


def _ros_workspace() -> Path:
    from backend.modules.warehouse.service.runtime_settings import ros2_workspace

    return ros2_workspace()


def _ros_distro_setup_path() -> str:
    distro = _safe_str(getattr(settings, "ROS_DISTRO", ""), "").strip() or "jazzy"
    configured = _safe_str(getattr(settings, "WAREHOUSE_ROS_SETUP_FILE", ""), "").strip()
    return configured or f"/opt/ros/{distro}/setup.bash"


def _sourced_ros_cmd(inner: str) -> list[str]:
    """Return a shell command that sources ROS and workspace setup safely.

    ``inner`` is still a shell fragment because most ROS CLI probes use shell
    helpers such as ``timeout``. Callers must quote user/config values before
    inserting them into ``inner``.
    """
    ws = _ros_workspace()
    setup = ws / "install" / "setup.bash"
    script_parts = [f"source {shlex.quote(_ros_distro_setup_path())}"]
    if setup.exists():
        script_parts.append(f"source {shlex.quote(str(setup))}")
    script_parts.append(inner)
    return ["bash", "-lc", " && ".join(script_parts)]


_CLOCK_PROBE_SCRIPT = r"""
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
    value = float(sec) + (float(nanosec) / 1_000_000_000.0)
    return value if math.isfinite(value) else None


async def _read_clock_once(timeout_s: float = 3.0) -> float | None:
    timeout_s = _safe_float(timeout_s, 3.0, min_value=0.5)
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            _sourced_ros_cmd(
                f"timeout {shlex.quote(str(max(2.0, timeout_s)))} ros2 topic echo /clock --once"
            ),
            env=ros_command_env(),
            capture_output=True,
            text=True,
            timeout=max(4.5, timeout_s + 2.0),
            check=False,
        )
    except Exception:
        logger.debug("Failed to read /clock once", exc_info=True)
        return None
    if result.returncode != 0:
        return None
    return _parse_clock_time(result.stdout)


def _normalize_clock_samples(raw_samples: object, *, max_samples: int = 256) -> list[float]:
    if not isinstance(raw_samples, list):
        return []
    samples: list[float] = []
    for sample in raw_samples[-max_samples:]:
        try:
            value = float(sample)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            samples.append(value)
    return samples


async def _probe_clock_with_rclpy_script(window: float) -> list[float]:
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
        if result.returncode != 0 and not result.stdout.strip():
            return []
        last_line = (result.stdout or "[]").splitlines()[-1]
        return _normalize_clock_samples(json.loads(last_line))
    except Exception:
        logger.debug("rclpy /clock probe failed", exc_info=True)
        return []


async def _probe_clock_with_cli_loop(window: float, poll_s: float) -> list[float]:
    deadline = time.monotonic() + max(0.5, window)
    samples: list[float] = []
    while time.monotonic() < deadline:
        remaining = max(0.5, deadline - time.monotonic())
        sample = await _read_clock_once(timeout_s=min(3.0, remaining))
        if sample is not None:
            samples.append(sample)
        await asyncio.sleep(max(0.1, poll_s))
    return _normalize_clock_samples(samples)


async def probe_clock_monotonic(
    *,
    window_s: float | None = None,
    poll_s: float = 0.25,
    max_forward_jump_s: float = 2.0,
) -> SimTimeStatus:
    window = max(0.5, _safe_float(window_s, _clock_stability_window_s()) if window_s is not None else _clock_stability_window_s())
    poll = _safe_float(poll_s, 0.25, min_value=0.05)
    max_forward = _safe_float(max_forward_jump_s, 2.0, min_value=0.0)

    samples = await _probe_clock_with_rclpy_script(window)
    if not samples:
        samples = await _probe_clock_with_cli_loop(window=min(window, 4.0), poll_s=poll)

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
            elif delta > max_forward:
                forward += 1
        previous = sample

    ok = jumps == 0 and frozen < max(2, len(samples) // 2) and forward == 0
    detail = "clock monotonic" if ok else "clock unstable"
    return SimTimeStatus(ok, detail, jumps, frozen, forward, samples)


async def probe_tf_broadcasters() -> SimTimeStatus:
    return await wait_for_tf_stable(timeout_s=1.5)


async def wait_for_tf_stable(
    *,
    timeout_s: float,
    parent_frame: str = "odom",
    child_frame: str = "base_link",
) -> SimTimeStatus:
    timeout_s = _safe_float(timeout_s, 1.5, min_value=0.1)
    deadline = time.monotonic() + timeout_s
    last_detail = "tf lookup failed"
    parent = shlex.quote(_safe_str(parent_frame, "odom"))
    child = shlex.quote(_safe_str(child_frame, "base_link"))

    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        cli_timeout = min(3.0, max(1.0, remaining + 0.5))
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                _sourced_ros_cmd(
                    f"timeout {shlex.quote(str(cli_timeout))} ros2 run tf2_ros tf2_echo {parent} {child}"
                ),
                env=ros_command_env(),
                capture_output=True,
                text=True,
                timeout=min(5.5, cli_timeout + 2.5),
                check=False,
            )
            stdout = result.stdout or ""
            if "At time" in stdout:
                return SimTimeStatus(True, "tf stable")
            last_detail = (result.stderr or stdout or "tf lookup failed")[:240]
        except Exception as exc:
            last_detail = str(exc)[:240]
        await asyncio.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
    return SimTimeStatus(False, last_detail)


async def wait_for_warehouse_map_tf_stable(
    *,
    timeout_s: float = 3.0,
    parent_frame: str = "warehouse_map",
    child_frame: str = "odom",
) -> SimTimeStatus:
    return await wait_for_tf_stable(
        timeout_s=timeout_s,
        parent_frame=parent_frame,
        child_frame=child_frame,
    )


def _is_target_nvblox_process(command: str) -> bool:
    return (
        "warehouse_nvblox.launch.py" in command
        or "__node:=nvblox_container" in command
        or "[nvblox_node]" in command
        or " nvblox_node" in command
    )


async def kill_stale_nvblox_processes(keep_pgids: set[int] | None = None) -> None:
    """Terminate orphaned nvBlox launch/container processes before restart.

    ``keep_pgids`` lists process-group ids that must NOT be killed (e.g. the
    currently tracked, healthy mapping stack which runs in its own session).
    Without this the warm preflight stack would be reaped and restarted.
    """
    protected = {int(p) for p in (keep_pgids or set()) if p}
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
        logger.debug("Could not list processes for stale nvBlox cleanup", exc_info=True)
        return
    if result.returncode != 0:
        return

    current_pid = os.getpid()
    try:
        current_pgid = os.getpgid(current_pid)
    except OSError:
        current_pgid = None

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
        if pid == current_pid or pgid <= 0 or pgid == current_pgid:
            continue
        if pid in protected or pgid in protected:
            continue
        if _is_target_nvblox_process(cmd):
            groups.add(pgid)

    if not groups:
        return

    for sig, delay in ((signal.SIGTERM, 0.8), (signal.SIGKILL, 0.0)):
        for pgid in list(groups):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                groups.discard(pgid)
            except PermissionError:
                groups.discard(pgid)
            except Exception:
                logger.debug("Failed to signal nvBlox process group pgid=%s", pgid, exc_info=True)
                groups.discard(pgid)
        if delay and groups:
            await asyncio.sleep(delay)
