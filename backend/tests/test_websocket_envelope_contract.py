from __future__ import annotations

import asyncio

import orjson
import pytest
from starlette.websockets import WebSocketState

from backend.core.events import MissionContextV1, TelemetryEnvelopeV1, TelemetryPayloadV1, utc_now
from backend.infrastructure.messaging.websocket_publisher import Client, TelemetryWebSocketManager


def _sample_envelope() -> TelemetryEnvelopeV1:
    return TelemetryEnvelopeV1(
        mission_runtime_id="flight-1",
        db_flight_id=1,
        sequence=1,
        emitted_at=utc_now(),
        source="test",
        mission=MissionContextV1(mission_id=1, org_id=9),
        payload=TelemetryPayloadV1.from_legacy_snapshot(
            {
                "position": {"lat": 41.0, "lon": 29.0, "alt": 12.0, "relative_alt": 8.0},
                "battery": {"remaining": 88},
                "mode": "GUIDED",
                "armed": True,
            },
            coalesced_message_count=1,
        ),
    )


def test_telemetry_envelope_legacy_wire_shape() -> None:
    envelope = _sample_envelope()
    message = envelope.to_websocket_message(wire_protocol="legacy")
    assert message["type"] == "telemetry"
    assert "protocol" not in message
    assert message["data"]["position"]["lat"] == 41.0
    assert message["data"]["mode"] == "GUIDED"


def test_telemetry_envelope_v1_wire_shape() -> None:
    envelope = _sample_envelope()
    message = envelope.to_websocket_message(wire_protocol="v1")
    assert message["type"] == "telemetry"
    assert message["protocol"] == "v1"
    assert message["envelope"]["kind"] == "telemetry"
    assert message["envelope"]["payload"]["position"]["lat"] == 41.0


@pytest.mark.asyncio
async def test_telemetry_broadcast_honors_client_wire_protocol() -> None:
    manager = TelemetryWebSocketManager()
    legacy_queue: asyncio.Queue[bytes] = asyncio.Queue()
    v1_queue: asyncio.Queue[bytes] = asyncio.Queue()

    class _Ws:
        client_state = WebSocketState.CONNECTED

    legacy_ws = _Ws()
    v1_ws = _Ws()
    manager._clients = {
        legacy_ws: Client(  # type: ignore[arg-type]
            ws=legacy_ws,  # type: ignore[arg-type]
            q=legacy_queue,
            task=asyncio.create_task(asyncio.sleep(3600)),
            connected_time=0.0,
            org_id=9,
            wire_protocol="legacy",
        ),
        v1_ws: Client(  # type: ignore[arg-type]
            ws=v1_ws,  # type: ignore[arg-type]
            q=v1_queue,
            task=asyncio.create_task(asyncio.sleep(3600)),
            connected_time=0.0,
            org_id=9,
            wire_protocol="v1",
        ),
    }

    envelope = _sample_envelope()
    await manager._local_broadcast_telemetry(envelope, org_id=9)

    legacy_msg = orjson.loads(legacy_queue.get_nowait())
    v1_msg = orjson.loads(v1_queue.get_nowait())

    assert legacy_msg["type"] == "telemetry"
    assert "protocol" not in legacy_msg
    assert legacy_msg["data"]["position"]["lat"] == 41.0

    assert v1_msg["protocol"] == "v1"
    assert v1_msg["envelope"]["payload"]["position"]["lat"] == 41.0
