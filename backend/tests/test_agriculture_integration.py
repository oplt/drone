from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.modules.agriculture.storage import AgricultureStorage
from backend.modules.agriculture.contracts import irrigation_zone_to_observation
from backend.entrypoints.workers.celery_app import celery_app

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_postgis_migrations_and_agriculture_tables_are_deployed():
    url = os.environ.get("DATABASE_URL")
    if not url or "sqlite" in url:
        pytest.skip("PostGIS integration database is not configured")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT PostGIS_Version()"))
            tables = set(await connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")))
            assert {"agriculture_flights", "agriculture_frame_lineage", "agriculture_analysis_runs"} <= tables
    finally:
        await engine.dispose()


def test_worker_routes_and_signed_storage_contract_are_registered(tmp_path: Path):
    assert celery_app.conf.task_routes["agriculture.process_run"]["queue"]
    assert celery_app.conf.task_routes["agriculture.stage.rgb_inference"]["queue"]
    storage = AgricultureStorage(tmp_path)
    assert storage.sign("org/7/exports/report.pdf").startswith("/agriculture/assets?")


def test_legacy_irrigation_observation_contract_preserves_source_lineage():
    class Zone:
        id = 1
        type = "standing_water"
        polygon_geojson = {"type": "Polygon", "coordinates": [[[4, 50], [4.001, 50], [4, 50]]]}
        severity = 0.8
        confidence = 0.7
        area_m2 = 12.0
        meta_data = {"mission_id": "mission-1", "analytics_version": "irrigation-v2"}
        evidence_image_ids = ["frame-1"]

    converted = irrigation_zone_to_observation(Zone())
    assert converted["uncertainty"]["source"] == "irrigation_analytics"
    assert converted["evidence_ids"] == ["frame-1"]
    assert converted["model_version"] == "irrigation-v2"
