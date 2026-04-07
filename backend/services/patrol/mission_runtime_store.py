"""Thin adapter that exposes active mission context to patrol/ML consumers.

The authoritative store is now ``MissionRuntimeRepository`` (DB-backed).
This module keeps the ``ActiveMissionRuntimeContext`` DTO and the
``mission_runtime_store`` singleton so existing callers need no changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.db.repository.mission_runtime_repo import mission_runtime_repo


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
    """Read-only view of the active mission runtime, backed by the DB repo."""

    async def get_active_context(self) -> Optional[ActiveMissionRuntimeContext]:
        row = await mission_runtime_repo.get_active()
        if row is None:
            return None
        return ActiveMissionRuntimeContext(
            client_flight_id=row.client_flight_id,
            mission_name=row.mission_name,
            mission_type=row.mission_type,
            state=row.state,
            db_flight_id=row.flight_id,
            private_patrol_task_type=row.private_patrol_task_type,
            ai_tasks=tuple(row.ai_tasks or ()),
        )


mission_runtime_store = MissionRuntimeStore()
