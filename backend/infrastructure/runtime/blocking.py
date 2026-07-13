"""Explicit boundaries for synchronous process, filesystem, and CPU work."""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from backend.observability import prometheus_metrics

T = TypeVar("T")


async def run_blocking(
    fn: Callable[..., T],
    *args: Any,
    boundary: str,
    operation: str,
    timeout_s: float | None = None,
    call_timeout_s: float | None = None,
    **kwargs: Any,
) -> T:
    """Run a blocking adapter operation off the event loop.

    ``wait_for`` bounds the caller's wait. Python cannot forcibly stop a running
    thread, so adapters must also enforce their own subprocess/SDK timeouts.
    """
    started = time.perf_counter()
    try:
        task = asyncio.to_thread(fn, *args, **kwargs)
        effective_timeout_s = call_timeout_s if call_timeout_s is not None else timeout_s
        if effective_timeout_s is None:
            return await task
        return await asyncio.wait_for(task, timeout=max(0.01, float(effective_timeout_s)))
    except Exception:
        prometheus_metrics.blocking_boundary_failures_total.labels(
            boundary=boundary,
            operation=operation,
        ).inc()
        raise
    finally:
        prometheus_metrics.blocking_boundary_duration_seconds.labels(
            boundary=boundary,
            operation=operation,
        ).observe(time.perf_counter() - started)


class BlockingProcessRunner:
    """Single process-launch adapter used by ROS and capture integrations."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        timeout: float | None = None,
        check: bool = False,
        text: bool = False,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[Any]:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=capture_output,
            timeout=timeout_s if timeout_s is not None else timeout,
            check=check,
            text=text,
        )

    async def run_async(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        timeout: float | None = None,
        check: bool = False,
        text: bool = False,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[Any]:
        process_timeout = timeout_s if timeout_s is not None else timeout
        return await run_blocking(
            self.run,
            argv,
            cwd=cwd,
            env=env,
            timeout=process_timeout,
            call_timeout_s=process_timeout,
            check=check,
            text=text,
            capture_output=capture_output,
            boundary="process",
            operation=str(argv[0]) if argv else "empty",
        )


blocking_process_runner = BlockingProcessRunner()
