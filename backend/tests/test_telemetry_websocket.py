from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import orjson
import pytest
from starlette.websockets import WebSocketState

from backend.core.events import MissionContextV1, TelemetryEnvelopeV1, TelemetryPayloadV1, utc_now
from backend.infrastructure.messaging.websocket_publisher import (
    Client,
    TelemetryWebSocketManager,
)
from backend.modules.telemetry.websocket_api import _authenticate_websocket


class _FakeWebSocket:
    def __init__(
        self,
        *,
        query_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> None:
        self.query_params = query_params or {}
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client_state = WebSocketState.CONNECTED


@pytest.mark.asyncio
async def test_websocket_auth_rejects_query_string_token() -> None:
    socket = _FakeWebSocket(query_params={"token": "leaked-jwt"})
    user, error = await _authenticate_websocket(socket)
    assert user is None
    assert error is not None
    assert "Query-string" in error


@pytest.mark.asyncio
async def test_websocket_auth_accepts_bearer_header(monkeypatch) -> None:
    async def fake_get_user(token, _db):
        assert token == "good-token"
        return SimpleNamespace(id=1, org_id=7)

    monkeypatch.setattr(
        "backend.modules.telemetry.websocket_api.get_user_from_token",
        fake_get_user,
    )
    monkeypatch.setattr(
        "backend.modules.telemetry.websocket_api.Session",
        lambda: AsyncMock(
            __aenter__=AsyncMock(return_value=object()),
            __aexit__=AsyncMock(return_value=False),
        ),
    )
    socket = _FakeWebSocket(headers={"authorization": "Bearer good-token"})
    user, error = await _authenticate_websocket(socket)
    assert error is None
    assert user is not None
    assert user.org_id == 7


@pytest.mark.asyncio
async def test_telemetry_fanout_is_scoped_by_org_id() -> None:
    manager = TelemetryWebSocketManager()
    org_a_queue: asyncio.Queue[bytes] = asyncio.Queue()
    org_b_queue: asyncio.Queue[bytes] = asyncio.Queue()

    class _Ws:
        client_state = WebSocketState.CONNECTED

    org_a_ws = _Ws()
    org_b_ws = _Ws()
    manager._clients = {
        org_a_ws: Client(  # type: ignore[arg-type]
            ws=org_a_ws,  # type: ignore[arg-type]
            q=org_a_queue,
            task=asyncio.create_task(asyncio.sleep(3600)),
            connected_time=0.0,
            org_id=10,
        ),
        org_b_ws: Client(  # type: ignore[arg-type]
            ws=org_b_ws,  # type: ignore[arg-type]
            q=org_b_queue,
            task=asyncio.create_task(asyncio.sleep(3600)),
            connected_time=0.0,
            org_id=20,
        ),
    }

    payload = orjson.dumps({"type": "telemetry", "data": {"mode": "AUTO"}})
    await manager._local_broadcast(payload, mission_runtime_id="flight-1", org_id=10)

    assert not org_a_queue.empty()
    assert org_b_queue.empty()

    manager._clients[org_a_ws].task.cancel()
    manager._clients[org_b_ws].task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await manager._clients[org_a_ws].task
    with pytest.raises(asyncio.CancelledError):
        await manager._clients[org_b_ws].task


@pytest.mark.asyncio
async def test_telemetry_fanout_honors_mission_subscription() -> None:
    manager = TelemetryWebSocketManager()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    class _Ws:
        client_state = WebSocketState.CONNECTED

    ws = _Ws()
    manager._clients = {
        ws: Client(  # type: ignore[arg-type]
            ws=ws,  # type: ignore[arg-type]
            q=queue,
            task=asyncio.create_task(asyncio.sleep(3600)),
            connected_time=0.0,
            org_id=10,
            mission_runtime_id="flight-a",
        ),
    }

    matching = orjson.dumps({"type": "telemetry", "data": {"mode": "AUTO"}})
    other = orjson.dumps({"type": "telemetry", "data": {"mode": "HOLD"}})

    await manager._local_broadcast(matching, mission_runtime_id="flight-a", org_id=10)
    await manager._local_broadcast(other, mission_runtime_id="flight-b", org_id=10)

    assert queue.qsize() == 1
    assert orjson.loads(queue.get_nowait())["data"]["mode"] == "AUTO"

    manager._clients[ws].task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await manager._clients[ws].task


@pytest.mark.asyncio
async def test_ingest_telemetry_envelope_forwards_org_id(monkeypatch) -> None:
    manager = TelemetryWebSocketManager()
    captured: dict[str, object] = {}

    async def capture_broadcast(*args, **kwargs):
        captured["kwargs"] = kwargs

    monkeypatch.setattr(manager, "_broadcast_telemetry_envelope", capture_broadcast)

    envelope = TelemetryEnvelopeV1(
        mission_runtime_id="flight-1",
        db_flight_id=1,
        sequence=1,
        emitted_at=utc_now(),
        source="test",
        mission=MissionContextV1(org_id=42),
        payload=TelemetryPayloadV1.from_legacy_snapshot({"mode": "AUTO"}, coalesced_message_count=1),
    )
    await manager.ingest_telemetry_envelope(envelope)

    assert captured["kwargs"]["org_id"] == 42
    assert captured["kwargs"]["mission_runtime_id"] == "flight-1"
