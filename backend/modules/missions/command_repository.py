"""Repository for OperatorCommand persistence."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, select

from backend.core.database.session import Session
from backend.modules.missions.command_models import OperatorCommand

logger = logging.getLogger(__name__)


class OperatorCommandRepository:
    def __init__(self, session_factory: type[Session] = Session) -> None:
        self._sf = session_factory

    async def create(
        self,
        *,
        command_id: str,
        client_flight_id: str,
        mission_runtime_id: int | None,
        command: str,
        idempotency_key: str,
        requested_by_user_id: int | None,
        state_before: str,
        state_after: str,
        accepted: bool,
        message: str,
        reason: str | None,
        requested_at: datetime,
    ) -> OperatorCommand:
        row = OperatorCommand(
            command_id=command_id,
            client_flight_id=client_flight_id,
            mission_runtime_id=mission_runtime_id,
            command=command,
            idempotency_key=idempotency_key,
            requested_by_user_id=requested_by_user_id,
            state_before=state_before,
            state_after=state_after,
            accepted=accepted,
            message=message,
            reason=reason,
            requested_at=requested_at,
        )
        async with self._sf() as s:
            s.add(row)
            await s.commit()
            await s.refresh(row)
        return row

    async def list_for_mission(
        self,
        client_flight_id: str,
        *,
        limit: int = 400,
    ) -> list[OperatorCommand]:
        async with self._sf() as s:
            result = await s.execute(
                select(OperatorCommand)
                .where(OperatorCommand.client_flight_id == client_flight_id)
                .order_by(OperatorCommand.requested_at.asc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_by_idempotency_key(
        self,
        client_flight_id: str,
        idempotency_key: str,
    ) -> OperatorCommand | None:
        async with self._sf() as s:
            result = await s.execute(
                select(OperatorCommand).where(
                    OperatorCommand.client_flight_id == client_flight_id,
                    OperatorCommand.idempotency_key == idempotency_key,
                )
            )
            return result.scalar_one_or_none()

    async def cleanup_old(self, *, older_than: datetime) -> int:
        """Delete operator command records whose requested_at is older than *older_than*.

        Returns the number of rows deleted.
        """
        async with self._sf() as s:
            result = await s.execute(
                delete(OperatorCommand).where(
                    OperatorCommand.requested_at <= older_than,
                )
            )
            await s.commit()
            return result.rowcount


operator_command_repo = OperatorCommandRepository()
