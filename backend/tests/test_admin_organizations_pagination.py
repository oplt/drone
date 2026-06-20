import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.modules.admin.api import list_organizations


def test_admin_organizations_are_paginated_with_total() -> None:
    row = SimpleNamespace(
        id=7,
        name="North Hub",
        slug="north-hub",
        user_count=3,
        created_at=datetime.now(UTC),
    )
    page_result = MagicMock()
    page_result.all.return_value = [row]
    total_result = MagicMock()
    total_result.scalar_one.return_value = 26
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[page_result, total_result])

    response = asyncio.run(list_organizations(page=2, page_size=25, db=db))

    assert response["organizations"][0]["id"] == 7
    assert response["total"] == 26
    assert response["page"] == 2
    assert response["page_size"] == 25
    assert db.execute.await_count == 2
    page_statement = db.execute.await_args_list[0].args[0]
    assert page_statement._limit_clause.value == 25
    assert page_statement._offset_clause.value == 25
