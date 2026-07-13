from __future__ import annotations

import asyncio
import shlex
from typing import Any

from backend.infrastructure.runtime.blocking import blocking_process_runner, run_blocking
from backend.infrastructure.warehouse.bridge_config import ros_command_env
from backend.modules.warehouse.service.frame_contract import REQUIRED_FRAME_EDGES
from backend.modules.warehouse.service.sim_time_tf_readiness import _sourced_ros_cmd

_DEFAULT_EDGE_TIMEOUT_S = 2.5
_MAX_CONCURRENT_EDGE_PROBES = 4


async def probe_ros_tf_edge(
    parent_frame: str,
    child_frame: str,
    *,
    timeout_s: float = _DEFAULT_EDGE_TIMEOUT_S,
) -> dict[str, Any]:
    parent = shlex.quote(str(parent_frame).strip())
    child = shlex.quote(str(child_frame).strip())
    cli_timeout = max(1.0, min(3.0, float(timeout_s)))
    try:
        result = await run_blocking(
            blocking_process_runner.run,
            _sourced_ros_cmd(
                f"timeout {shlex.quote(str(cli_timeout))} ros2 run tf2_ros tf2_echo {parent} {child}"
            ),
            env=ros_command_env(),
            capture_output=True,
            text=True,
            timeout=cli_timeout + 2.5,
            boundary="process",
            operation="ros_tf_edge_probe",
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        ok = "At time" in stdout and "Failure" not in stderr
        detail = None if ok else (stderr or stdout or "tf lookup failed")[:240]
        return {
            "parent_frame": str(parent_frame),
            "child_frame": str(child_frame),
            "tf_ok": ok,
            "detail": detail,
        }
    except Exception as exc:
        return {
            "parent_frame": str(parent_frame),
            "child_frame": str(child_frame),
            "tf_ok": False,
            "detail": str(exc)[:240],
        }


async def probe_warehouse_ros_tf_tree(
    *,
    edges: frozenset[tuple[str, str]] | None = None,
    timeout_s: float = _DEFAULT_EDGE_TIMEOUT_S,
) -> dict[str, Any]:
    """Probe canonical warehouse TF edges via tf2_echo (best-effort, non-blocking)."""
    probe_edges = sorted(edges or REQUIRED_FRAME_EDGES)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EDGE_PROBES)

    async def _probe_edge(parent: str, child: str) -> dict[str, Any]:
        async with semaphore:
            return await probe_ros_tf_edge(parent, child, timeout_s=timeout_s)

    edge_results = await asyncio.gather(
        *(_probe_edge(parent, child) for parent, child in probe_edges)
    )
    missing_edges = [
        f"{edge['parent_frame']}->{edge['child_frame']}"
        for edge in edge_results
        if not edge.get("tf_ok")
    ]
    ok_count = sum(1 for edge in edge_results if edge.get("tf_ok"))
    return {
        "tf_ok": ok_count == len(edge_results) and len(edge_results) > 0,
        "edge_count": len(edge_results),
        "ok_count": ok_count,
        "missing_edges": missing_edges,
        "edges": edge_results,
    }
