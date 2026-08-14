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
                            "'idx_webhook_delivery_endpoint_status_created', "
                            "'uq_agri_active_capability_release')"
                        )
                    )
                )
                migration_states = set(
                    await connection.scalars(
                        text(
                            "SELECT DISTINCT migration_state "
                            "FROM agriculture_model_versions"
                        )
                    )
                )
                video_indexes = set(
                    await connection.scalars(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE schemaname = 'public' AND indexname IN "
                            "('ix_video_analysis_jobs_status', "
                            "'ix_video_analysis_jobs_status_lease', "
                            "'ix_video_assets_status', "
                            "'uq_agri_telemetry_receipt_flight_key')"
                        )
                    )
                )
            assert postgis
            assert revision == "l5m6n7o8p9q0"
            assert index_names == {
                "idx_mission_runtime_client_state",
                "idx_webhook_delivery_endpoint_status_created",
                "uq_agri_active_capability_release",
            }
            assert video_indexes == {
                "ix_video_analysis_jobs_status",
                "ix_video_analysis_jobs_status_lease",
                "ix_video_assets_status",
                "uq_agri_telemetry_receipt_flight_key",
            }
            assert migration_states <= {"linked", "quarantined", "legacy_unlinked"}
        finally:
            await engine.dispose()

    asyncio.run(probe())
