"""Warehouse live-map readiness — tf probe."""

from __future__ import annotations

import shlex

from backend.infrastructure.runtime.blocking import blocking_process_runner, run_blocking

from . import deps


async def probe_mapping_tf_degraded(
    *,
    parent_frame: str = "odom",
    child_frame: str = "base_link",
) -> dict[str, object]:
    """Best-effort TF probe for diagnostics; never gates takeoff."""
    from backend.modules.warehouse.service.sim_time_tf_readiness import _sourced_ros_cmd

    env = deps.resolve("ros_command_env")()
    try:
        result = await run_blocking(
            blocking_process_runner.run,
            _sourced_ros_cmd(
                "timeout 3.0 ros2 run tf2_ros tf2_echo "
                f"{shlex.quote(parent_frame)} {shlex.quote(child_frame)}"
            ),
            env=env,
            capture_output=True,
            text=True,
            timeout=5.5,
            boundary="process",
            operation="ros_mapping_tf_probe",
        )
        stdout = result.stdout or ""
        ok = "At time" in stdout
        detail = None if ok else (result.stderr or stdout or "tf lookup failed")[:240]
        return {
            "tf_ok": ok,
            "parent_frame": parent_frame,
            "child_frame": child_frame,
            "degraded": not ok,
            "detail": detail,
        }
    except Exception as exc:
        return {
            "tf_ok": False,
            "parent_frame": parent_frame,
            "child_frame": child_frame,
            "degraded": True,
            "detail": str(exc)[:240],
        }
