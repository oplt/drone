from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.infrastructure.vehicle import mavlink_client
from backend.infrastructure.vehicle.mavlink_client import MavlinkDrone
from backend.modules.media import api as media_api


class _FakeVideoRuntime:
    async def ensure_running(self) -> dict:
        raise RuntimeError("Timed out waiting for first video frame.")

    async def status(self) -> dict:
        return {
            "source": "udp://127.0.0.1:5600",
            "error": "Timed out waiting for first video frame.",
        }


@pytest.mark.asyncio
async def test_mjpeg_proxy_returns_503_when_camera_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(media_api, "shared_video_runtime", _FakeVideoRuntime())

    with pytest.raises(HTTPException) as exc_info:
        await media_api.mjpeg_proxy(SimpleNamespace(), user=object())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["message"] == "Camera unavailable"


def _fake_vehicle() -> SimpleNamespace:
    return SimpleNamespace(
        home_location=None,
        location=SimpleNamespace(
            local_frame=SimpleNamespace(north=1.0, east=2.0, down=-1.0),
            global_frame=SimpleNamespace(lat=None, lon=None),
        ),
    )


def test_local_frame_home_fallback_allowed_in_sim(monkeypatch) -> None:
    monkeypatch.setattr(mavlink_client, "connect", lambda *args, **kwargs: _fake_vehicle())

    drone = MavlinkDrone("udp:127.0.0.1:14550", heartbeat_timeout=1.0)
    drone.connect(home_fallback_allowed=True)

    assert drone.home_source == "local_frame_origin"


def test_real_flight_blocks_local_frame_home_fallback(monkeypatch) -> None:
    monkeypatch.setattr(mavlink_client, "connect", lambda *args, **kwargs: _fake_vehicle())
    monkeypatch.setattr(mavlink_client.time, "sleep", lambda _seconds: None)

    drone = MavlinkDrone("udp:127.0.0.1:14550", heartbeat_timeout=1.0)

    with pytest.raises(RuntimeError, match="GPS home is required"):
        drone.connect(home_fallback_allowed=False)

