from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from typing import Literal, Any
from urllib.parse import urlparse

import httpx

from backend.infrastructure.warehouse.bridge_stack_process import (
    BridgeStackStatus,
    get_warehouse_bridge_stack_manager,
)




WarehouseBridgeState = Literal[
    "stopped",
    "starting",
    "process_running",
    "ready",
    "degraded",
    "failed",
    "stopping",
]


def configured_bridge_url() -> str:
    raw = os.getenv("WAREHOUSE_ROS_BRIDGE_URL", "http://127.0.0.1:8088").strip()
    if not raw:
        raw = "http://127.0.0.1:8088"
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw.rstrip("/")


def validate_bridge_url_config() -> tuple[bool, str | None]:
    parsed = urlparse(configured_bridge_url())
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme not in {"http", "https"}:
        return False, "WAREHOUSE_ROS_BRIDGE_URL must use http or https"
    if port != 8088:
        return (
            False,
            "WAREHOUSE_ROS_BRIDGE_URL port does not match scripts/warehouse_bridge.sh default 8088",
        )
    return True, None

def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WarehouseBridgeSupervisorStatus:
    state: WarehouseBridgeState
    running: bool
    bridge_url: str
    pid: int | None = None
    run_id: str | None = None
    last_error: str | None = None
    last_exit_code: int | None = None
    restart_count: int = 0
    last_started_at: str | None = None
    last_ready_at: str | None = None
    circuit_open: bool = False
    process: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "running": self.running,
            "bridge_url": self.bridge_url,
            "pid": self.pid,
            "run_id": self.run_id,
            "last_error": self.last_error,
            "last_exit_code": self.last_exit_code,
            "restart_count": self.restart_count,
            "last_started_at": self.last_started_at,
            "last_ready_at": self.last_ready_at,
            "circuit_open": self.circuit_open,
            "process": self.process,
        }


class WarehouseBridgeSupervisor:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._startup_task: asyncio.Task[WarehouseBridgeSupervisorStatus] | None = None
        self._state: WarehouseBridgeState = "stopped"
        self._last_error: str | None = None
        self._last_exit_code: int | None = None
        self._restart_count = 0
        self._restart_attempts: list[float] = []
        self._last_started_at: str | None = None
        self._last_ready_at: str | None = None
        self._circuit_open = False
        self._last_process: BridgeStackStatus | None = None

    async def ensure_ready(self, *, deep: bool | None = None) -> WarehouseBridgeSupervisorStatus:
        deep_ready = (
            deep
            if deep is not None
            else _env_bool("WAREHOUSE_BRIDGE_SUPERVISOR_DEEP_READY", "1")
        )

        async with self._lock:
            current = await self.status()
            if current.state == "ready":
                return current
            if self._circuit_open:
                return current
            if self._startup_task is not None and not self._startup_task.done():
                task = self._startup_task
            elif current.running and current.state in {
                "starting",
                "process_running",
                "degraded",
            }:
                return current
            else:
                if self._startup_task is None or self._startup_task.done():
                    self._startup_task = asyncio.create_task(
                        self._start_until_ready(deep=deep_ready)
                    )
                task = self._startup_task

        return await task


    async def status(self) -> WarehouseBridgeSupervisorStatus:
        process = await asyncio.to_thread(get_warehouse_bridge_stack_manager().status)
        self._last_process = process

        if process.last_exit_code is not None:
            self._last_exit_code = process.last_exit_code
        if process.last_error:
            self._last_error = process.last_error

        if not process.running and self._state in {
            "starting",
            "process_running",
            "ready",
            "degraded",
        }:
            self._state = "failed" if process.last_exit_code not in (None, 0) else "stopped"

        return self._snapshot(process)


    async def stop(self, *, reason: str = "manual_stop") -> WarehouseBridgeSupervisorStatus:
        async with self._lock:
            self._state = "stopping"
            process = get_warehouse_bridge_stack_manager().stop(reason=reason)
            self._state = "stopped"
            self._last_process = process
            return self._snapshot(process)

    async def reset(self) -> WarehouseBridgeSupervisorStatus:
        async with self._lock:
            self._circuit_open = False
            self._restart_count = 0
            self._restart_attempts.clear()
            self._last_error = None
            self._state = "stopped"
            self._startup_task = None
        return await self.ensure_ready()


    async def _start_until_ready(self, *, deep: bool) -> WarehouseBridgeSupervisorStatus:
        max_attempts = max(1, int(os.getenv("WAREHOUSE_BRIDGE_MAX_RESTARTS", "3")))
        window_s = float(os.getenv("WAREHOUSE_BRIDGE_RESTART_WINDOW_S", "120"))
        grace_s = float(os.getenv("WAREHOUSE_BRIDGE_STARTUP_GRACE_S", "2.0"))
        readiness_attempts = int(os.getenv("WAREHOUSE_BRIDGE_READINESS_ATTEMPTS", "30"))
        readiness_interval_s = float(os.getenv("WAREHOUSE_BRIDGE_READINESS_INTERVAL_S", "0.5"))

        manager = get_warehouse_bridge_stack_manager()
        last_process: BridgeStackStatus | None = None

        for attempt in range(max_attempts):
            now = time.monotonic()
            self._restart_attempts = [
                item for item in self._restart_attempts if now - item < window_s
            ]

            if len(self._restart_attempts) >= max_attempts:
                self._circuit_open = True
                self._state = "failed"
                self._last_error = "warehouse bridge restart circuit breaker open"
                return await self.status()

            self._restart_attempts.append(now)
            self._restart_count += 1
            self._state = "starting"

            process = await asyncio.to_thread(
                manager.start,
                restart=attempt > 0,
                stop_reason="process_exited_retry",
            )
            last_process = process
            self._last_process = process
            self._last_started_at = process.started_at
            self._last_error = process.last_error
            self._last_exit_code = process.last_exit_code

            if not process.running:
                self._state = "failed"
                self._last_error = process.last_error or "warehouse bridge stack did not start"
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(min(1.0 + attempt, 5.0))
                    continue
                return self._snapshot(process)

            self._state = "process_running"
            await asyncio.sleep(max(0.0, grace_s))

            ready, detail = await self._wait_basic_ready(
                attempts=readiness_attempts,
                interval_s=readiness_interval_s,
                deep=deep,
            )

            process = await asyncio.to_thread(manager.status)
            last_process = process
            self._last_process = process
            self._last_exit_code = process.last_exit_code

            if ready:
                self._state = "ready"
                self._last_error = None
                self._last_ready_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                return self._snapshot(process)

            self._last_error = detail or f"{configured_bridge_url()} did not become ready"

            # Key lifecycle fix:
            # Do NOT restart an alive ROS/Gazebo graph just because deep readiness is not green yet.
            # Return degraded so the UI/preflight can show blockers.
            if process.running:
                self._state = "degraded"
                return self._snapshot(process)

            self._state = "failed"
            if attempt + 1 < max_attempts:
                await asyncio.sleep(min(1.0 + attempt, 5.0))

        self._circuit_open = True
        self._state = "failed"
        self._last_error = self._last_error or "warehouse bridge did not become ready"
        return self._snapshot(last_process)


    async def _wait_basic_ready(
            self,
            *,
            attempts: int,
            interval_s: float,
            deep: bool,
    ) -> tuple[bool, str | None]:
        url = configured_bridge_url()
        path = "/health?deep=1&force=1" if deep else "/health"
        timeout = httpx.Timeout(2.0 if deep else 1.0, connect=0.75)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for index in range(max(1, attempts)):
                try:
                    response = await client.get(f"{url}{path}")
                    if response.status_code >= 500:
                        detail = f"bridge health returned HTTP {response.status_code}"
                    elif response.status_code >= 400:
                        detail = f"bridge health returned HTTP {response.status_code}"
                    else:
                        payload: dict[str, Any] = response.json()
                        ready_raw = payload.get("ready", payload.get("healthy"))

                        if ready_raw is True:
                            return True, None

                        # For shallow checks, a valid JSON health endpoint is enough.
                        # For Gazebo startup, deep=True requires ready/healthy=True.
                        if not deep and ready_raw is None:
                            return True, None

                        components = payload.get("components")
                        status = payload.get("status")
                        detail = (
                                str(payload.get("detail") or "")
                                or f"bridge health status={status!r} ready={ready_raw!r} components={components!r}"
                        )

                    self._last_error = detail
                except Exception as exc:
                    detail = str(exc).strip() or type(exc).__name__
                    self._last_error = detail

                if index + 1 < attempts:
                    process = await asyncio.to_thread(get_warehouse_bridge_stack_manager().status)
                    self._last_process = process
                    if not process.running:
                        self._last_error = (
                            process.last_error
                            or f"warehouse bridge stack exited with code {process.last_exit_code}"
                        )
                        self._last_exit_code = process.last_exit_code
                        return False, self._last_error
                    backoff = interval_s * (1.5 ** min(index, 5)) + random.uniform(0, 0.15)
                    await asyncio.sleep(min(backoff, 5.0))

        return False, self._last_error

    def _snapshot(
        self, process: BridgeStackStatus | None = None
    ) -> WarehouseBridgeSupervisorStatus:
        proc = process or self._last_process
        running = bool(proc.running) if proc else False
        return WarehouseBridgeSupervisorStatus(
            state=self._state,
            running=running,
            bridge_url=configured_bridge_url(),
            pid=proc.pid if proc else None,
            run_id=proc.run_id if proc else None,
            last_error=self._last_error or (proc.last_error if proc else None),
            last_exit_code=self._last_exit_code
            if self._last_exit_code is not None
            else (proc.last_exit_code if proc else None),
            restart_count=self._restart_count,
            last_started_at=self._last_started_at or (proc.started_at if proc else None),
            last_ready_at=self._last_ready_at,
            circuit_open=self._circuit_open,
            process=proc.to_dict() if proc else {},
        )


_supervisor: WarehouseBridgeSupervisor | None = None


def get_warehouse_bridge_supervisor() -> WarehouseBridgeSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = WarehouseBridgeSupervisor()
    return _supervisor


def reset_warehouse_bridge_supervisor_for_tests() -> None:
    global _supervisor
    _supervisor = None
