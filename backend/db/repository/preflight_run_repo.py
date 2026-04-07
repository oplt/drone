"""Repository for PreflightRun persistence.

Replaces the module-global _preflight_runs dict + threading.Lock in routes_flights.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from backend.db.models import PreflightRun
from backend.db.session import Session

logger = logging.getLogger(__name__)


class PreflightRunRepository:
    def __init__(self, session_factory: type[Session] = Session) -> None:
        self._sf = session_factory

    async def create(
        self,
        *,
        run_uuid: str,
        user_id: Optional[int],
        mission_type: str,
        mission_name: Optional[str] = None,
        mission_fingerprint: Optional[str] = None,
        overall_status: str,
        base_checks: List[Dict[str, Any]],
        mission_checks: List[Dict[str, Any]],
        critical_failures: List[str],
        summary: Dict[str, Any],
        vehicle_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> PreflightRun:
        now = datetime.now(timezone.utc)
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

    async def get_by_uuid(self, run_uuid: str) -> Optional[PreflightRun]:
        async with self._sf() as s:
            result = await s.execute(
                select(PreflightRun).where(PreflightRun.run_uuid == run_uuid)
            )
            return result.scalar_one_or_none()

    async def get_by_uuid_for_user(
        self, run_uuid: str, user_id: int
    ) -> Optional[PreflightRun]:
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
        now = datetime.now(timezone.utc)
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
