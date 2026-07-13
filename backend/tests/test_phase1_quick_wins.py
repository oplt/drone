from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon


def test_production_security_rejects_development_defaults() -> None:
    from backend.core.config.production import validate_production_security

    settings = SimpleNamespace(
        app_env="production",
        jwt_secret="local-dev-secret-CHANGE-ME",
        warehouse_live_map_ingest_token="dev-live-map-ingest",
        storage_backend="s3",
        s3_secret_key="minioadmin",
        database_url="postgresql://drone:drone@example.test/drone",
        cookie_secure=False,
        photogrammetry_public_static_assets=True,
    )
    bootstrap = SimpleNamespace(settings_vault_key="")

    with pytest.raises(RuntimeError, match="Production security validation failed"):
        validate_production_security(settings, bootstrap)


def test_production_security_allows_non_production() -> None:
    from backend.core.config.production import validate_production_security

    validate_production_security(SimpleNamespace(app_env="local"))


@pytest.mark.asyncio
async def test_risk_engine_isolation_fetches_positions_once() -> None:
    from backend.modules.livestock.models import Animal, AnimalPosition
    from backend.modules.livestock.risk_service import RiskEngine

    first = Animal(id=1, collar_id="a-1", herd_id=7, is_active=True)
    second = Animal(id=2, collar_id="a-2", herd_id=7, is_active=True)
    first_position = AnimalPosition(animal_id=1, lat=50.0, lon=4.0)
    second_position = AnimalPosition(animal_id=2, lat=50.01, lon=4.0)

    class Result:
        def all(self):
            return [(first_position, first), (second_position, second)]

    class FakeDB:
        calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return Result()

    db = FakeDB()
    alerts = await RiskEngine().isolation_alerts(db, herd_id=7, threshold_m=1)

    assert db.calls == 1
    assert len(alerts) == 2


@pytest.mark.asyncio
async def test_irrigation_asset_requires_owned_mission_and_stays_in_root(
    tmp_path, monkeypatch
) -> None:
    from backend.modules.irrigation import asset_access

    mission_dir = tmp_path / "mission-1" / "captures"
    mission_dir.mkdir(parents=True)
    asset = mission_dir / "capture.jpg"
    asset.write_bytes(b"image")
    (mission_dir / "1.json").write_bytes(b"internal metadata")
    monkeypatch.setattr(asset_access.settings, "irrigation_storage_dir", str(tmp_path))

    class FakeService:
        async def get_owned_mission(self, _db, *, mission_id, user):
            return object() if mission_id == "mission-1" and user == "owner" else None

    monkeypatch.setattr(asset_access, "IrrigationProcessingService", FakeService)

    assert (
        await asset_access.resolve_owned_asset(
            object(), asset_path="mission-1/captures/capture.jpg", user="owner"
        )
    ) == asset
    assert (
        await asset_access.resolve_owned_asset(
            object(), asset_path="mission-1/captures/capture.jpg", user="other"
        )
    ) is None
    assert (
        await asset_access.resolve_owned_asset(
            object(), asset_path="mission-1/../secret.txt", user="owner"
        )
    ) is None
    assert (
        await asset_access.resolve_owned_asset(
            object(), asset_path="mission-1/captures/1.json", user="owner"
        )
    ) is None
    nested_asset = mission_dir / "nested.png"
    nested_asset.write_bytes(b"image")
    assert (
        await asset_access.resolve_owned_asset(
            object(), asset_path="mission-1/captures/nested.png", user="owner"
        )
    ) is not None
    nested_dir = mission_dir / "nested"
    nested_dir.mkdir()
    nested_file = nested_dir / "capture.jpg"
    nested_file.write_bytes(b"image")
    assert (
        await asset_access.resolve_owned_asset(
            object(), asset_path="mission-1/captures/nested/capture.jpg", user="owner"
        )
    ) is None

    outside = tmp_path.parent / "outside.jpg"
    outside.write_bytes(b"secret")
    (mission_dir / "linked.jpg").symlink_to(outside)
    assert (
        await asset_access.resolve_owned_asset(
            object(), asset_path="mission-1/captures/linked.jpg", user="owner"
        )
    ) is None


def test_irrigation_assets_use_authorized_route_not_static_mount() -> None:
    from fastapi.routing import APIRoute
    from starlette.routing import Mount

    from backend.entrypoints.api.app import app
    from backend.modules.identity.dependencies import require_org_user

    assert not any(
        isinstance(route, Mount) and route.path == "/irrigation-assets"
        for route in app.routes
    )
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/irrigation-assets/{asset_path:path}"
    )
    assert route.endpoint.__module__ == "backend.modules.irrigation.asset_api"
    assert any(dependency.call is require_org_user for dependency in route.dependant.dependencies)


@pytest.mark.asyncio
async def test_risk_engine_boundary_uses_one_latest_position_query() -> None:
    from backend.modules.geofences.models import Geofence
    from backend.modules.livestock.models import Animal, AnimalPosition
    from backend.modules.livestock.risk_service import RiskEngine

    geofence = Geofence(
        id=9,
        name="pasture",
        polygon=from_shape(Polygon([(3, 49), (5, 49), (5, 51), (3, 51), (3, 49)]), srid=4326),
    )
    animal = Animal(id=1, collar_id="a-1", herd_id=7, is_active=True)
    position = AnimalPosition(animal_id=1, lat=52.0, lon=4.0)

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def all(self):
            return [(position, animal)]

    class FakeDB:
        calls = 0

    async def execute_with_rows(statement):
        db.calls += 1
        return Result(geofence)

    db = FakeDB()
    db.execute = execute_with_rows
    alerts = await RiskEngine().boundary_exit_alerts(db, herd_id=7, pasture_geofence_id=9)

    assert db.calls == 1
    assert alerts[0]["type"] == "boundary_exit"


@pytest.mark.asyncio
async def test_analytics_cache_is_org_scoped_and_typed() -> None:
    from backend.modules.analytics.cache import get_cached_overview, set_cached_overview

    class FakeRedis:
        values: ClassVar[dict[str, str]] = {}

        async def get(self, key):
            return self.values.get(key)

        async def set(self, key, value, ex):
            self.values[key] = value
            self.ttl = ex

    redis = FakeRedis()
    await set_cached_overview(redis, 42, {"summary": {"active_flights": 1}}, ttl=45)

    assert await get_cached_overview(redis, 42) == {"summary": {"active_flights": 1}}
    assert await get_cached_overview(redis, 43) is None
    assert redis.ttl == 45


@pytest.mark.asyncio
async def test_analytics_cache_hit_skips_database_queries(monkeypatch) -> None:
    from backend.modules.analytics import api

    class FakeRedis:
        async def get(self, key):
            assert key == "analytics:overview:v1:org:42"
            return '{"summary": {"active_flights": 3}}'

    class FakeDB:
        calls = 0

        async def execute(self, _statement):
            self.calls += 1
            raise AssertionError("analytics cache hit must not query the database")

        async def scalar(self, _statement):
            self.calls += 1
            raise AssertionError("analytics cache hit must not query the database")

    monkeypatch.setattr(api, "get_redis_client", lambda: FakeRedis())
    result = await api.overview(
        db=FakeDB(),
        org_user=SimpleNamespace(org_id=42),
    )

    assert result == {"summary": {"active_flights": 3}}


@pytest.mark.asyncio
async def test_alert_polling_list_has_no_n_plus_one_queries() -> None:
    from backend.modules.alerts.repository import AlertRepository

    class Rows:
        class Scalars:
            def all(self):
                return []

        def scalars(self):
            return self.Scalars()

    class FakeDB:
        calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return Rows()

        async def scalar(self, _statement):
            self.calls += 1
            return 0

    db = FakeDB()
    items, total = await AlertRepository().list_alerts(db, org_id=42)

    assert items == []
    assert total == 0
    assert db.calls == 2


@pytest.mark.asyncio
async def test_upload_validation_rejects_wrong_type_and_empty_files(tmp_path) -> None:
    from backend.modules.irrigation.upload_validation import (
        validate_image_metadata,
        write_bounded_upload,
    )

    with pytest.raises(ValueError, match="must be an image"):
        validate_image_metadata(
            SimpleNamespace(filename="capture.jpg", content_type="text/plain"),
            allowed_extensions={".jpg"},
        )

    class EmptyUpload:
        async def read(self, _size):
            return b""

    with pytest.raises(ValueError, match="empty"):
        await write_bounded_upload(
            EmptyUpload(),
            tmp_path / "capture.jpg",
            max_bytes=1024,
        )
