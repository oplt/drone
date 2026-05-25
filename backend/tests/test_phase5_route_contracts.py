from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from backend.core.database.session import get_db
from backend.core.errors.handlers import register_error_handlers
from backend.modules.fields import api as routes_field
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.identity.models import User, UserRole


async def _empty_db() -> AsyncGenerator[object, None]:
    yield object()


def _user(*, user_id: int = 11, org_id: int = 7, role: UserRole = UserRole.org_admin) -> User:
    return User(
        id=user_id,
        org_id=org_id,
        role=role,
        email=f"user-{user_id}@example.test",
        hashed_password="not-used",
    )


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(routes_field.router)
    app.dependency_overrides[get_db] = _empty_db
    return app


async def _request(app: FastAPI, method: str, path: str, **kwargs: Any) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://phase5.test"
    ) as client:
        return await client.request(method, path, **kwargs)


def test_field_routes_require_authentication() -> None:
    response = asyncio.run(_request(_app(), "GET", "/fields"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_field_creation_uses_server_authenticated_owner(monkeypatch: Any) -> None:
    created_by: list[int] = []

    class _FieldService:
        async def create(
            self, db: object, *, user: Any, name: str, polygon: Any
        ) -> SimpleNamespace:
            created_by.append(user.id)
            return SimpleNamespace(id=19, owner_id=user.id, name=name, area_ha=2.5)

    async def org_writer() -> OrgUser:
        user = _user()
        return OrgUser(user=user, org_id=user.org_id)

    app = _app()
    app.dependency_overrides[require_org_write] = org_writer
    monkeypatch.setattr(routes_field, "field_service", _FieldService())

    response = asyncio.run(
        _request(
            app,
            "POST",
            "/fields",
            json={
                "name": "west",
                "owner_id": 999,
                "coordinates": [[4.0, 50.0], [4.001, 50.0], [4.001, 50.001]],
            },
        )
    )

    assert response.status_code == 200
    assert response.json()["owner_id"] == 11
    assert created_by == [11]


def test_cross_tenant_field_access_returns_not_found(monkeypatch: Any) -> None:
    class _FieldService:
        async def get_owned(self, db: object, *, field_id: int, user: Any) -> None:
            return None

    async def org_reader() -> OrgUser:
        user = _user()
        return OrgUser(user=user, org_id=user.org_id)

    app = _app()
    app.dependency_overrides[require_org_user] = org_reader
    monkeypatch.setattr(routes_field, "field_service", _FieldService())

    response = asyncio.run(_request(app, "GET", "/fields/99"))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Field not found"
