"""Repository for MissionRuntime persistence.

Replaces the module-global in-memory dicts and locks in routes_flights.py.
All methods are async and use the shared SQLAlchemy session factory.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from backend.modules.missions.domain.state_machine import (
    ACTIVE_STATES,
    TERMINAL_STATES,
)
from backend.modules.missions.runtime_models import MissionRuntime

logger = logging.getLogger(__name__)


class MissionRuntimeReadMixin:
    async def get_by_client_id(self, client_flight_id: str) -> MissionRuntime | None:
        async with self._sf() as s:
            result = await s.execute(
                select(MissionRuntime).where(MissionRuntime.client_flight_id == client_flight_id)
            )
            return result.scalar_one_or_none()

    async def get_by_client_id_for_user(
        self, client_flight_id: str, user_id: int
    ) -> MissionRuntime | None:
        async with self._sf() as s:
            result = await s.execute(
                select(MissionRuntime).where(
                    MissionRuntime.client_flight_id == client_flight_id,
                    MissionRuntime.user_id == user_id,
                )
            )
            return result.scalar_one_or_none()

    async def get_active(self) -> MissionRuntime | None:
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
        self, *, user_id: int | None = None, limit: int = 50
    ) -> list[MissionRuntime]:
        async with self._sf() as s:
            q = select(MissionRuntime).order_by(MissionRuntime.created_at.desc()).limit(limit)
            if user_id is not None:
                q = q.where(MissionRuntime.user_id == user_id)
            result = await s.execute(q)
            return list(result.scalars().all())

    async def list_resumable(
        self,
        *,
        user_id: int | None = None,
        limit: int = 50,
    ) -> list[MissionRuntime]:
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
