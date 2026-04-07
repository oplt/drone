"""Repository for MissionRuntime persistence.

Replaces the module-global in-memory dicts and locks in routes_flights.py.
All methods are async and use the shared SQLAlchemy session factory.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import MissionRuntime
from backend.db.session import Session
from backend.flight.state_machine import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    is_terminal,
    validate_transition,
)

logger = logging.getLogger(__name__)


class MissionRuntimeRepository:
    def __init__(self, session_factory: type[Session] = Session) -> None:
        self._sf = session_factory

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        client_flight_id: str,
        user_id: Optional[int],
        mission_name: str,
        mission_type: str,
        mission_task_type: Optional[str] = None,
        private_patrol_task_type: Optional[str] = None,
        preflight_run_uuid: Optional[str] = None,
        ai_tasks: List[str] | None = None,
        state: str = "queued",
        mission_params: Dict[str, Any] | None = None,
    ) -> MissionRuntime:
        row = MissionRuntime(
            client_flight_id=client_flight_id,
            user_id=user_id,
            mission_name=mission_name,
            mission_type=mission_type,
            mission_task_type=mission_task_type,
            private_patrol_task_type=private_patrol_task_type,
            preflight_run_uuid=preflight_run_uuid,
            ai_tasks=list(ai_tasks or []),
            state=state,
            mission_params=mission_params or {},
            resume_metadata={},
            command_audit=[],
            idempotency_results={},
        )
        async with self._sf() as s:
            s.add(row)
            await s.commit()
            await s.refresh(row)
        return row

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_client_id(
        self, client_flight_id: str
    ) -> Optional[MissionRuntime]:
        async with self._sf() as s:
            result = await s.execute(
                select(MissionRuntime).where(
                    MissionRuntime.client_flight_id == client_flight_id
                )
            )
            return result.scalar_one_or_none()

    async def get_by_client_id_for_user(
        self, client_flight_id: str, user_id: int
    ) -> Optional[MissionRuntime]:
        async with self._sf() as s:
            result = await s.execute(
                select(MissionRuntime).where(
                    MissionRuntime.client_flight_id == client_flight_id,
                    MissionRuntime.user_id == user_id,
                )
            )
            return result.scalar_one_or_none()

    async def get_active(self) -> Optional[MissionRuntime]:
        """Return the single non-terminal mission runtime, or None."""
        async with self._sf() as s:
            result = await s.execute(
                select(MissionRuntime)
                .where(MissionRuntime.state.in_(ACTIVE_STATES))
                .order_by(MissionRuntime.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def list_recent(
        self, *, user_id: Optional[int] = None, limit: int = 50
    ) -> List[MissionRuntime]:
        async with self._sf() as s:
            q = select(MissionRuntime).order_by(MissionRuntime.created_at.desc()).limit(limit)
            if user_id is not None:
                q = q.where(MissionRuntime.user_id == user_id)
            result = await s.execute(q)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Update — state transitions
    # ------------------------------------------------------------------

    async def set_state(
        self,
        client_flight_id: str,
        *,
        state: str,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        skip_transition_validation: bool = False,
    ) -> bool:
        """Update lifecycle state. Returns True if the row existed.

        Raises ValueError if the transition is invalid according to the state
        machine, unless *skip_transition_validation* is True.
        """
        now = datetime.now(timezone.utc)
        values: Dict[str, Any] = {"state": state, "updated_at": now}
        if error:
            values["failure_reason"] = error
        if started_at:
            values["started_at"] = started_at
        if ended_at:
            values["ended_at"] = ended_at
        elif is_terminal(state):
            values["ended_at"] = now

        async with self._sf() as s:
            if not skip_transition_validation:
                current = await s.execute(
                    select(MissionRuntime.state).where(
                        MissionRuntime.client_flight_id == client_flight_id
                    )
                )
                current_state = current.scalar_one_or_none()
                if current_state is not None and not validate_transition(current_state, state):
                    raise ValueError(
                        f"Invalid state transition: {current_state!r} → {state!r} "
                        f"for mission {client_flight_id!r}"
                    )
            result = await s.execute(
                update(MissionRuntime)
                .where(MissionRuntime.client_flight_id == client_flight_id)
                .values(**values)
                .returning(MissionRuntime.id)
            )
            await s.commit()
            return result.scalar_one_or_none() is not None

    async def set_flight_id(
        self, client_flight_id: str, *, flight_id: int
    ) -> None:
        async with self._sf() as s:
            await s.execute(
                update(MissionRuntime)
                .where(MissionRuntime.client_flight_id == client_flight_id)
                .values(flight_id=flight_id, updated_at=datetime.now(timezone.utc))
            )
            await s.commit()

    # ------------------------------------------------------------------
    # Update — command audit + idempotency
    # ------------------------------------------------------------------

    async def apply_command(
        self,
        client_flight_id: str,
        *,
        new_state: str,
        audit_entry: Dict[str, Any],
        idempotency_key: str,
        idempotency_response: Dict[str, Any],
    ) -> Optional[MissionRuntime]:
        """Atomically transition state, append audit entry, and cache idempotency result.

        Returns the updated row, or None if not found.
        """
        async with self._sf() as s:
            result = await s.execute(
                select(MissionRuntime)
                .where(MissionRuntime.client_flight_id == client_flight_id)
                .with_for_update()
            )
            row: Optional[MissionRuntime] = result.scalar_one_or_none()
            if row is None:
                return None

            if not validate_transition(row.state, new_state):
                raise ValueError(
                    f"Invalid state transition: {row.state!r} → {new_state!r} "
                    f"for mission {client_flight_id!r}"
                )

            row.state = new_state
            row.updated_at = datetime.now(timezone.utc)
            if is_terminal(new_state):
                row.ended_at = row.updated_at

            # Append audit entry (JSON list mutation — load, append, reassign)
            audit_list = list(row.command_audit or [])
            audit_list.append(audit_entry)
            if len(audit_list) > 400:
                audit_list = audit_list[-400:]
            row.command_audit = audit_list

            # Update idempotency cache
            idem = dict(row.idempotency_results or {})
            idem[idempotency_key] = idempotency_response
            row.idempotency_results = idem

            await s.commit()
            await s.refresh(row)
        return row

    async def get_idempotency_result(
        self, client_flight_id: str, idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        row = await self.get_by_client_id(client_flight_id)
        if row is None:
            return None
        return (row.idempotency_results or {}).get(idempotency_key)

    async def update_operator_note(
        self, client_flight_id: str, note: str
    ) -> None:
        async with self._sf() as s:
            await s.execute(
                update(MissionRuntime)
                .where(MissionRuntime.client_flight_id == client_flight_id)
                .values(operator_note=note, updated_at=datetime.now(timezone.utc))
            )
            await s.commit()


    async def list_resumable(
        self,
        *,
        user_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[MissionRuntime]:
        """Return terminal missions that have non-empty resume_metadata and mission_params."""
        async with self._sf() as s:
            from sqlalchemy import cast
            from sqlalchemy.dialects.postgresql import JSONB
            q = (
                select(MissionRuntime)
                .where(
                    MissionRuntime.state.in_(TERMINAL_STATES),
                    MissionRuntime.resume_metadata != cast({}, JSONB),
                    MissionRuntime.mission_params != cast({}, JSONB),
                )
                .order_by(MissionRuntime.created_at.desc())
                .limit(limit)
            )
            if user_id is not None:
                q = q.where(MissionRuntime.user_id == user_id)
            result = await s.execute(q)
            return list(result.scalars().all())

    async def cleanup_terminal(self, *, older_than: datetime) -> int:
        """Delete terminal mission runtimes whose ended_at is older than *older_than*.

        Returns the number of rows deleted.  Active/non-terminal runtimes are
        never touched by this method.
        """
        async with self._sf() as s:
            result = await s.execute(
                delete(MissionRuntime).where(
                    MissionRuntime.state.in_(TERMINAL_STATES),
                    MissionRuntime.ended_at != None,  # noqa: E711
                    MissionRuntime.ended_at <= older_than,
                )
            )
            await s.commit()
            return result.rowcount


mission_runtime_repo = MissionRuntimeRepository()
