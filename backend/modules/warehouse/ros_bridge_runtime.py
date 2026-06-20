from __future__ import annotations

import asyncio
import shlex
import subprocess
from pathlib import Path

from backend.core.config.runtime import settings
from backend.infrastructure.warehouse.bridge_config import quick_ros_bridge_check, ros_command_env

_bridge_process: subprocess.Popen[bytes] | None = None
_bridge_lock = asyncio.Lock()

def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ros2_workspace() -> Path:
    raw = settings.warehouse_ros2_ws.strip()
    return Path(raw or str(_project_root() / "ros2_ws")).resolve()


async def ensure_ros_bridge_running(*, start: bool) -> tuple[bool | None, str]:
    global _bridge_process
    ws = ros2_workspace()
    probe_ok, probe_detail = await asyncio.to_thread(quick_ros_bridge_check, ws)
    if probe_ok is True:
        return True, probe_detail
    if not start:
        return probe_ok, probe_detail

    async with _bridge_lock:
        if _bridge_process is not None and _bridge_process.poll() is None:
            await asyncio.sleep(0.5)
            probe_ok, probe_detail = await asyncio.to_thread(quick_ros_bridge_check, ws)
            if probe_ok is True:
                return True, probe_detail
            return None, f"Bridge process running; waiting for topics. {probe_detail}"

        setup = ws / "install" / "setup.bash"
        if not setup.exists():
            return False, f"ROS 2 workspace is not built: {setup}"

        log_dir = Path("backend/storage/warehouse_ros/logs").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "warehouse_bridge.log"
        cmd = (
            "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
            f"source {shlex.quote(str(setup))} && "
            "ros2 launch drone_gz_bridge warehouse_bridge.launch.py"
        )
        env = ros_command_env()
        try:
            with log_path.open("ab") as log_file:
                _bridge_process = subprocess.Popen(
                    ["bash", "-lc", cmd],
                    cwd=str(ws),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
        except FileNotFoundError:
            return False, "bash is not available; cannot start ROS 2 bridge."
        except Exception as exc:
            return False, f"Failed starting ROS 2 bridge: {exc}"

    grace_s = settings.warehouse_bridge_startup_grace_s
    await asyncio.sleep(max(0.2, min(grace_s, 5.0)))
    probe_ok, probe_detail = await asyncio.to_thread(quick_ros_bridge_check, ws)
    if probe_ok is True:
        return True, f"Started ROS 2 bridge. {probe_detail}"
    if _bridge_process is not None and _bridge_process.poll() is not None:
        return False, f"ROS 2 bridge exited early. Check {log_path}. {probe_detail}"
    return None, f"ROS 2 bridge process started, but topics are not visible yet. {probe_detail}"
