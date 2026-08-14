from __future__ import annotations

from backend.infrastructure.runtime.blocking import blocking_process_runner
from backend.infrastructure.warehouse.bridge_config.ros_env import ros_command_env


def list_gz_topics() -> tuple[set[str], str | None]:
    result = blocking_process_runner.run(
        ["bash", "-lc", "gz topic -l"],
        capture_output=True,
        timeout=3,
        check=False,
        env=ros_command_env(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        return set(), detail or "gz topic -l failed."
    return {
        line.strip()
        for line in result.stdout.decode(errors="replace").splitlines()
        if line.strip()
    }, None

