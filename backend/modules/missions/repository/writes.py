"""Repository for MissionRuntime persistence.

Replaces the module-global in-memory dicts and locks in routes_flights.py.
All methods are async and use the shared SQLAlchemy session factory.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update

from backend.modules.missions.domain.state_machine import (
    TERMINAL_STATES,
    is_terminal,
    validate_transition,
)
from backend.modules.missions.flight_models import Flight
from backend.modules.missions.runtime_models import MissionRuntime

logger = logging.getLogger(__name__)


class MissionRuntimeWriteMixin:
    async def create(
        self,
        *,
        client_flight_id: str,
        user_id: int | None,
        org_id: int | None,
        project_id: int | None,
        mission_name: str,
        mission_type: str,
        mission_task_type: str | None = None,
        private_patrol_task_type: str | None = None,
        preflight_run_uuid: str | None = None,
        ai_tasks: list[str] | None = None,
        state: str = "queued",
        mission_params: dict[str, Any] | None = None,
    ) -> MissionRuntime:
        row = MissionRuntime(
            client_flight_id=client_flight_id,
            user_id=user_id,
            org_id=org_id,
            project_id=project_id,
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

    async def set_state(
        self,
        client_flight_id: str,
        *,
        state: str,
        error: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        skip_transition_validation: bool = False,
    ) -> bool:
        """Update lifecycle state. Returns True if the row existed.

        Raises ValueError if the transition is invalid according to the state
        machine, unless *skip_transition_validation* is True.
        """
        now = datetime.now(UTC)
        values: dict[str, Any] = {"state": state, "updated_at": now}
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

    async def set_flight_id(self, client_flight_id: str, *, flight_id: int) -> None:
        async with self._sf() as s:
            runtime_result = await s.execute(
                select(MissionRuntime).where(MissionRuntime.client_flight_id == client_flight_id)
            )
            runtime = runtime_result.scalar_one_or_none()
            await s.execute(
                update(MissionRuntime)
                .where(MissionRuntime.client_flight_id == client_flight_id)
                .values(flight_id=flight_id, updated_at=datetime.now(UTC))
            )
            if runtime is not None:
                await s.execute(
                    update(Flight)
                    .where(Flight.id == flight_id)
                    .values(
                        org_id=runtime.org_id,
                        project_id=runtime.project_id,
                    )
                )
            await s.commit()

    async def apply_command(
        self,
        client_flight_id: str,
        *,
        new_state: str,
        audit_entry: dict[str, Any],
        idempotency_key: str,
        idempotency_response: dict[str, Any],
    ) -> MissionRuntime | None:
        """Atomically transition state, append audit entry, and cache idempotency result.

        Returns the updated row, or None if not found.
        """
        async with self._sf() as s:
            result = await s.execute(
                select(MissionRuntime)
                .where(MissionRuntime.client_flight_id == client_flight_id)
                .with_for_update()
            )
            row: MissionRuntime | None = result.scalar_one_or_none()
            if row is None:
                return None

            if not validate_transition(row.state, new_state):
                raise ValueError(
                    f"Invalid state transition: {row.state!r} → {new_state!r} "
                    f"for mission {client_flight_id!r}"
                )

            row.state = new_state
            row.updated_at = datetime.now(UTC)
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
    ) -> dict[str, Any] | None:
        row = await self.get_by_client_id(client_flight_id)
        if row is None:
            return None
        return (row.idempotency_results or {}).get(idempotency_key)

    async def update_operator_note(self, client_flight_id: str, note: str) -> None:
        async with self._sf() as s:
            await s.execute(
                update(MissionRuntime)
                .where(MissionRuntime.client_flight_id == client_flight_id)
                .values(operator_note=note, updated_at=datetime.now(UTC))
            )
            await s.commit()

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
