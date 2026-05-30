from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from backend.infrastructure.warehouse.perception import DisabledWarehousePerceptionPort
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.identity.models import User, UserRole
from backend.modules.warehouse import api as warehouse_routes
from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
    WarehousePerceptionStatus,
    WarehouseReplayStartRequest,
)


def _user() -> User:
    return User(
        id=1,
        org_id=7,
        role=UserRole.org_admin,
        email="operator@example.test",
        hashed_password="not-used",
    )


async def _org_user() -> OrgUser:
    user = _user()
    return OrgUser(user=user, org_id=user.org_id)


class _FakePerceptionPort:
    async def status(self) -> WarehousePerceptionStatus:
        return WarehousePerceptionStatus(
            configured=True,
            reachable=True,
            ready=True,
            status="ready",
            profile="isaac_ros_nvblox_stereo",
            bridge_url="http://jetson.test",
            websocket_url="ws://jetson.test/ws",
            capture_root="/data/warehouse",
            components={"visual_slam": True, "nvblox": True},
        )

    async def start_mapping(
        self, request: WarehouseMappingStartRequest
    ) -> WarehousePerceptionCommandResult:
        del request
        return WarehousePerceptionCommandResult(accepted=True, status="accepted")

    async def stop_mapping(self, *, flight_id: str) -> WarehousePerceptionCommandResult:
        del flight_id
        return WarehousePerceptionCommandResult(accepted=True, status="stopped")

    async def download_artifacts(self, *, flight_id: str, destination_dir: Path) -> list[str]:
        del flight_id, destination_dir
        return []

    async def start_replay(
        self, request: WarehouseReplayStartRequest
    ) -> WarehousePerceptionCommandResult:
        del request
        return WarehousePerceptionCommandResult(accepted=True, status="accepted")

    async def stop_replay(self, *, replay_id: str) -> WarehousePerceptionCommandResult:
        del replay_id
        return WarehousePerceptionCommandResult(accepted=True, status="stopped")


def _app(monkeypatch: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(warehouse_routes.router)
    app.dependency_overrides[require_org_user] = _org_user
    monkeypatch.setattr(
        warehouse_routes,
        "get_warehouse_perception_port",
        lambda: _FakePerceptionPort(),
    )
    return app


async def _request(app: FastAPI, method: str, path: str) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://warehouse.test"
    ) as client:
        return await client.request(method, path)


def test_warehouse_perception_health_route(monkeypatch: Any) -> None:
    response = asyncio.run(_request(_app(monkeypatch), "GET", "/warehouse/perception/health"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["reachable"] is True
    assert payload["ready"] is True
    assert payload["profile"] == "isaac_ros_nvblox_stereo"
    assert payload["components"] == {"visual_slam": True, "nvblox": True}


def test_disabled_perception_port_reports_configuration_gap() -> None:
    port = DisabledWarehousePerceptionPort(
        profile="isaac_ros_nvblox_stereo",
        bridge_url="",
        websocket_url="",
        capture_root="/tmp/warehouse",
    )

    status = asyncio.run(port.status())

    assert status.configured is False
    assert status.reachable is False
    assert status.ready is False
    assert status.status == "disabled"
    assert "WAREHOUSE_ROS_BRIDGE_URL" in (status.detail or "")
