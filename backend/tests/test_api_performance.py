from __future__ import annotations

import orjson

from backend.core.config.runtime import bootstrap
from backend.core.database import session as db_session


def test_engine_kwargs_postgres_pool_uses_bootstrap_settings(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap, "database_pool_size", 15)
    monkeypatch.setattr(bootstrap, "database_max_overflow", 25)
    kwargs = db_session._engine_kwargs("postgresql+asyncpg://localhost/drone")
    assert kwargs["pool_size"] == 15
    assert kwargs["pool_recycle"] == 1800
    assert kwargs["max_overflow"] == 25


def test_engine_kwargs_sqlite_omits_pool_size() -> None:
    kwargs = db_session._engine_kwargs("sqlite+aiosqlite:///tmp/test.db")
    assert "pool_size" not in kwargs
    assert kwargs["pool_pre_ping"] is True


def test_orjson_response_serializes_geojson() -> None:
    from backend.shared.json_responses import orjson_response

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [4.0, 50.0]},
            "properties": {"id": index},
        }
        for index in range(100)
    ]
    payload = {"type": "FeatureCollection", "features": features}
    response = orjson_response(payload, headers={"etag": '"abc"'})
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["etag"] == '"abc"'
    parsed = orjson.loads(response.body)
    assert len(parsed["features"]) == 100
