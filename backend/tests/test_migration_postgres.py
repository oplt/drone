from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.core.config.runtime import settings

pytestmark = pytest.mark.integration


def test_postgresql_postgis_and_request_path_indexes() -> None:
    """Smoke-test the deployed schema on the real PostgreSQL/PostGIS service."""

    async def probe() -> None:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        try:
            async with engine.connect() as connection:
                postgis = await connection.scalar(text("SELECT PostGIS_Version()"))
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                index_names = set(
                    await connection.scalars(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE schemaname = 'public' AND indexname IN "
                            "('idx_mission_runtime_client_state', "
                            "'idx_webhook_delivery_endpoint_status_created')"
                        )
                    )
                )
            assert postgis
            assert revision == "v8c4d5e6f7a8"
            assert index_names == {
                "idx_mission_runtime_client_state",
                "idx_webhook_delivery_endpoint_status_created",
            }
        finally:
            await engine.dispose()

    asyncio.run(probe())
