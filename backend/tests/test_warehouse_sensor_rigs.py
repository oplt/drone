from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.identity.models import User, UserRole
from backend.modules.warehouse import api as warehouse_routes
from backend.modules.warehouse.ports import WarehousePerceptionStatus


async def _empty_db() -> AsyncGenerator[object, None]:
    yield object()


def _user() -> User:
    return User(
        id=11,
        org_id=7,
        role=UserRole.org_admin,
        email="warehouse@example.test",
        hashed_password="not-used",
    )


async def _org_user() -> OrgUser:
    user = _user()
    return OrgUser(user=user, org_id=user.org_id)


def _rig(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": 3,
        "name": "Jetson stereo rig",
        "camera_model": "ZED X",
        "stereo_baseline_m": 0.12,
        "intrinsics_url": "/calibration/intrinsics.yaml",
        "extrinsics_url": "/calibration/extrinsics.yaml",
        "imu_transform_json": {"frame": "imu_link"},
        "firmware_version": "1.2.3",
        "isaac_ros_version": "3.2",
        "calibration_status": "valid",
        "calibration_hash": "abc123",
        "calibration_meta": {"rms_px": 0.3},
        "active": True,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeWarehouseApplication:
    def __init__(self) -> None:
        self.rig = _rig()

    async def list_sensor_rigs(self, db: object, *, user: User, limit: int) -> list[Any]:
        del db, user, limit
        return [self.rig]

    async def get_sensor_rig(
        self, db: object, *, sensor_rig_id: int, user: User
    ) -> Any | None:
        del db, user
        return self.rig if sensor_rig_id == self.rig.id else None

    async def create_sensor_rig(self, db: object, *, user: User, payload: Any) -> Any:
        del db, user
        self.rig = _rig(name=payload.name, camera_model=payload.camera_model)
        return self.rig

    async def update_sensor_rig_calibration(
        self, db: object, *, rig: Any, payload: Any
    ) -> Any:
        del db
        rig.calibration_status = payload.calibration_status
        rig.calibration_hash = payload.calibration_hash
        rig.calibration_meta = payload.calibration_meta
        return rig

    async def delete_sensor_rig(self, db: object, *, rig: Any) -> None:
        del db
        rig.active = False


class _FakePerceptionPort:
    async def status(self) -> WarehousePerceptionStatus:
        return WarehousePerceptionStatus(
            configured=True,
            reachable=True,
            ready=True,
            status="ready",
            profile="isaac_ros_nvblox_stereo",
            bridge_url="http://jetson.test",
            components={"visual_slam": True, "nvblox": True},
        )


def _app(monkeypatch: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(warehouse_routes.router)
    app.dependency_overrides[get_db] = _empty_db
    app.dependency_overrides[require_org_user] = _org_user
    app.dependency_overrides[require_org_write] = _org_user
    monkeypatch.setattr(warehouse_routes, "warehouse_application", _FakeWarehouseApplication())
    monkeypatch.setattr(
        warehouse_routes,
        "get_warehouse_perception_port",
        lambda: _FakePerceptionPort(),
    )
    return app


async def _request(app: FastAPI, method: str, path: str, **kwargs: Any) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://warehouse.test"
    ) as client:
        return await client.request(method, path, **kwargs)


def test_sensor_rig_list_and_health(monkeypatch: Any) -> None:
    app = _app(monkeypatch)

    list_response = asyncio.run(_request(app, "GET", "/warehouse/sensor-rigs"))
    health_response = asyncio.run(_request(app, "GET", "/warehouse/sensor-rigs/3/health"))

    assert list_response.status_code == 200
    assert list_response.json()[0]["calibration_status"] == "valid"
    assert health_response.status_code == 200
    assert health_response.json()["ready"] is True
    assert health_response.json()["blockers"] == []


def test_sensor_rig_calibration_update(monkeypatch: Any) -> None:
    app = _app(monkeypatch)

    response = asyncio.run(
        _request(
            app,
            "POST",
            "/warehouse/sensor-rigs/3/calibration",
            json={
                "calibration_status": "failed",
                "calibration_hash": "def456",
                "calibration_meta": {"reason": "bad reprojection"},
            },
        )
    )

    assert response.status_code == 200
    assert response.json()["calibration_status"] == "failed"
    assert response.json()["calibration_hash"] == "def456"
