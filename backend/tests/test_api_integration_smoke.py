from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_or_openapi_available(api_client) -> None:
    response = await api_client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert "paths" in payload
    assert "/warehouse/preflight" in payload["paths"]
    assert "/warehouse/live-map/config" in payload["paths"]
    assert "/warehouse/flight/readiness" in payload["paths"]


@pytest.mark.asyncio
async def test_warehouse_preflight_requires_auth(api_client) -> None:
    response = await api_client.get("/warehouse/preflight")
    assert response.status_code in {401, 403}
