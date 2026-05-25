from __future__ import annotations

import asyncio
from typing import Any

from backend.modules.alerts.repository import AlertRepository
from backend.modules.livestock.repository import LivestockRepository


class _Scalars:
    def all(self) -> list[Any]:
        return []


class _Result:
    def scalars(self) -> _Scalars:
        return _Scalars()


class _CaptureSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, stmt) -> _Result:
        self.statements.append(str(stmt))
        return _Result()

    async def scalar(self, stmt) -> int:
        self.statements.append(str(stmt))
        return 0


def test_alert_listing_and_count_are_scoped_to_organization() -> None:
    session = _CaptureSession()
    repo = AlertRepository()

    asyncio.run(repo.list_alerts(session, org_id=41))
    asyncio.run(repo.count_open_alerts(session, org_id=41))

    assert all("operational_alerts.org_id" in stmt for stmt in session.statements)


def test_livestock_collections_are_scoped_through_herd_organization() -> None:
    session = _CaptureSession()
    repo = LivestockRepository()

    asyncio.run(repo.list_herds(session, org_id=41))
    asyncio.run(repo.list_animals(session, org_id=41))
    asyncio.run(repo.list_tasks(session, org_id=41, herd_id=3))

    assert all("herds.org_id" in stmt for stmt in session.statements)
