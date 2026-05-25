"""Repository for PreflightRun persistence.

Replaces the module-global _preflight_runs dict + threading.Lock in routes_flights.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from backend.core.database.session import Session
from backend.modules.preflight.models import PreflightRun

logger = logging.getLogger(__name__)


class PreflightRunRepository:
    def __init__(self, session_factory: type[Session] = Session) -> None:
        self._sf = session_factory

    async def create(
        self,
        *,
        run_uuid: str,
        user_id: int | None,
        mission_type: str,
        mission_name: str | None = None,
        mission_fingerprint: str | None = None,
        overall_status: str,
        base_checks: list[dict[str, Any]],
        mission_checks: list[dict[str, Any]],
        critical_failures: list[str],
        summary: dict[str, Any],
        vehicle_id: str | None = None,
        expires_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> PreflightRun:
        now = datetime.now(UTC)
        row = PreflightRun(
            run_uuid=run_uuid,
            user_id=user_id,
            mission_type=mission_type,
            mission_name=mission_name,
            mission_fingerprint=mission_fingerprint,
            overall_status=overall_status,
            base_checks=base_checks,
            mission_checks=mission_checks,
            critical_failures=critical_failures,
            summary=summary,
            vehicle_id=vehicle_id,
            expires_at=expires_at,
            started_at=now,
            completed_at=completed_at or now,
            operator_acknowledged_warnings=False,
        )
        async with self._sf() as s:
            s.add(row)
            await s.commit()
            await s.refresh(row)
        return row

    async def get_by_uuid(self, run_uuid: str) -> PreflightRun | None:
        async with self._sf() as s:
            result = await s.execute(select(PreflightRun).where(PreflightRun.run_uuid == run_uuid))
            return result.scalar_one_or_none()

    async def get_by_uuid_for_user(self, run_uuid: str, user_id: int) -> PreflightRun | None:
        async with self._sf() as s:
            result = await s.execute(
                select(PreflightRun).where(
                    PreflightRun.run_uuid == run_uuid,
                    PreflightRun.user_id == user_id,
                )
            )
            return result.scalar_one_or_none()

    async def cleanup_expired(self) -> int:
        """Delete expired preflight runs. Returns count deleted."""
        now = datetime.now(UTC)
        async with self._sf() as s:
            result = await s.execute(
                delete(PreflightRun).where(
                    PreflightRun.expires_at != None,  # noqa: E711
                    PreflightRun.expires_at <= now,
                )
            )
            await s.commit()
            return result.rowcount


preflight_run_repo = PreflightRunRepository()
