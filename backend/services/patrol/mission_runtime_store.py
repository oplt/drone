from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Literal, List


MissionLifecycleState = Literal[
    "queued",
    "running",
    "paused",
    "aborted",
    "completed",
    "failed",
]


@dataclass
class MissionCommandAuditRecord:
    command_id: str
    command: str
    idempotency_key: str
    requested_by_user_id: int
    requested_at: float
    state_before: str
    state_after: str
    accepted: bool
    message: str
    reason: Optional[str] = None


@dataclass
class MissionRuntimeRecord:
    client_flight_id: str
    user_id: int
    mission_name: str
    mission_type: str
    preflight_run_id: Optional[str]
    state: MissionLifecycleState
    created_at: float
    updated_at: float
    db_flight_id: Optional[int] = None
    last_error: Optional[str] = None

    # add this so ML can distinguish actual patrol subtype
    private_patrol_task_type: Optional[str] = None
    ai_tasks: tuple[str, ...] = ()

    command_audit: List[MissionCommandAuditRecord] = field(default_factory=list)
    idempotency_results: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class ActiveMissionRuntimeContext:
    client_flight_id: str
    mission_name: str
    mission_type: str
    state: str
    db_flight_id: Optional[int]
    private_patrol_task_type: Optional[str]
    ai_tasks: tuple[str, ...]


class MissionRuntimeStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_runtime_id: Optional[str] = None
        self._runtimes: dict[str, MissionRuntimeRecord] = {}

    async def put(self, runtime: MissionRuntimeRecord, *, make_active: bool = False) -> None:
        async with self._lock:
            self._runtimes[runtime.client_flight_id] = runtime
            if make_active:
                self._active_runtime_id = runtime.client_flight_id

    async def get(self, flight_id: str) -> Optional[MissionRuntimeRecord]:
        async with self._lock:
            return self._runtimes.get(flight_id)

    async def get_active(self) -> Optional[MissionRuntimeRecord]:
        async with self._lock:
            if not self._active_runtime_id:
                return None
            return self._runtimes.get(self._active_runtime_id)

    async def get_active_context(self) -> Optional[ActiveMissionRuntimeContext]:
        async with self._lock:
            if not self._active_runtime_id:
                return None
            rec = self._runtimes.get(self._active_runtime_id)
            if rec is None:
                return None
            return ActiveMissionRuntimeContext(
                client_flight_id=rec.client_flight_id,
                mission_name=rec.mission_name,
                mission_type=rec.mission_type,
                state=rec.state,
                db_flight_id=rec.db_flight_id,
                private_patrol_task_type=rec.private_patrol_task_type,
                ai_tasks=tuple(rec.ai_tasks or ()),
            )

    async def set_db_flight_id(self, flight_id: str, db_flight_id: Optional[int]) -> None:
        async with self._lock:
            rec = self._runtimes.get(flight_id)
            if rec is None:
                return
            rec.db_flight_id = db_flight_id
            rec.updated_at = time.time()

    async def set_state(
            self,
            flight_id: str,
            *,
            state: str,
            error: Optional[str] = None,
    ) -> None:
        async with self._lock:
            rec = self._runtimes.get(flight_id)
            if rec is None:
                return
            rec.state = state
            rec.updated_at = time.time()
            if error:
                rec.last_error = error
            if state in {"aborted", "completed", "failed"} and self._active_runtime_id == flight_id:
                self._active_runtime_id = None

    async def clear_active_if_matches(self, flight_id: str) -> None:
        async with self._lock:
            if self._active_runtime_id == flight_id:
                self._active_runtime_id = None


mission_runtime_store = MissionRuntimeStore()