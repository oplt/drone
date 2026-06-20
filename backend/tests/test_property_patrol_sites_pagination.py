import asyncio
from unittest.mock import AsyncMock, MagicMock

from backend.modules.property_patrol.api import (
    list_incidents,
    list_missions,
    list_sensor_events,
    list_sites,
    list_templates,
)


def test_property_patrol_sites_are_paginated() -> None:
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db = MagicMock()
    db.scalars = AsyncMock(return_value=scalar_result)

    response = asyncio.run(list_sites(limit=25, offset=50, user=MagicMock(), db=db))

    assert response == []
    db.scalars.assert_awaited_once()
    statement = db.scalars.await_args.args[0]
    assert statement._limit_clause.value == 25
    assert statement._offset_clause.value == 50


def test_property_patrol_templates_are_paginated() -> None:
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db = MagicMock()
    db.scalars = AsyncMock(return_value=scalar_result)

    response = asyncio.run(
        list_templates(site_id=7, limit=20, offset=40, user=MagicMock(), db=db)
    )

    assert response == []
    db.scalars.assert_awaited_once()
    statement = db.scalars.await_args.args[0]
    assert statement._limit_clause.value == 20
    assert statement._offset_clause.value == 40


def test_property_patrol_missions_are_paginated() -> None:
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db = MagicMock()
    db.scalars = AsyncMock(return_value=scalar_result)

    response = asyncio.run(
        list_missions(site_id=7, limit=15, offset=30, user=MagicMock(), db=db)
    )

    assert response == []
    db.scalars.assert_awaited_once()
    statement = db.scalars.await_args.args[0]
    assert statement._limit_clause.value == 15
    assert statement._offset_clause.value == 30


def test_property_patrol_sensor_events_are_paginated() -> None:
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db = MagicMock()
    db.scalars = AsyncMock(return_value=scalar_result)

    response = asyncio.run(
        list_sensor_events(site_id=7, limit=10, offset=20, user=MagicMock(), db=db)
    )

    assert response == []
    db.scalars.assert_awaited_once()
    statement = db.scalars.await_args.args[0]
    assert statement._limit_clause.value == 10
    assert statement._offset_clause.value == 20


def test_property_patrol_incidents_are_paginated() -> None:
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db = MagicMock()
    db.scalars = AsyncMock(return_value=scalar_result)

    response = asyncio.run(
        list_incidents(site_id=7, limit=5, offset=10, user=MagicMock(), db=db)
    )

    assert response == []
    db.scalars.assert_awaited_once()
    statement = db.scalars.await_args.args[0]
    assert statement._limit_clause.value == 5
    assert statement._offset_clause.value == 10
