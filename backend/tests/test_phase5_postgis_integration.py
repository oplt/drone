from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.modules.fields.models import Field
from backend.modules.fields.repository import FieldRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"),
]


def test_field_repository_computes_area_with_postgis() -> None:
    async def run() -> float:
        engine = create_async_engine(str(TEST_DATABASE_URL))
        try:
            async with engine.begin() as connection:
                await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
                await connection.execute(
                    text(
                        "CREATE TEMP TABLE fields "
                        "(id integer PRIMARY KEY, boundary geometry(POLYGON, 4326)) "
                        "ON COMMIT DROP"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO fields (id, boundary) VALUES "
                        "(1, ST_GeomFromText("
                        "'POLYGON((4 50,4.001 50,4.001 50.001,4 50.001,4 50))', 4326))"
                    )
                )
                field = Field(id=1, name="integration", boundary=None)
                async with AsyncSession(bind=connection) as session:
                    await FieldRepository._refresh_area(session, field)
                assert field.area_ha is not None
                return field.area_ha
        finally:
            await engine.dispose()

    assert asyncio.run(run()) > 0
