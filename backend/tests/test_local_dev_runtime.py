from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.infrastructure.vehicle import mavlink_client
from backend.infrastructure.vehicle.mavlink_client import MavlinkDrone
from backend.modules.media import api as media_api


class _FakeVideoRuntime:
    def source_url(self) -> str:
        return "udp://127.0.0.1:5600"

    async def ensure_running(self) -> dict:
        raise RuntimeError("Timed out waiting for first video frame.")

    async def status(self) -> dict:
        return {
            "source": "udp://127.0.0.1:5600",
            "error": "Timed out waiting for first video frame.",
        }

    async def readiness_status(self) -> dict:
        return {
            **await self.status(),
            "state": "unavailable",
            "first_frame_available": False,
            "retry_after_ms": 5000,
            "failure_count": 1,
        }


@pytest.mark.asyncio
async def test_mjpeg_proxy_waits_for_drone_link(monkeypatch) -> None:
    class _Runtime(_FakeVideoRuntime):
        ensure_calls = 0

        async def ensure_running(self) -> dict:
            self.ensure_calls += 1
            return await super().ensure_running()

    fake = _Runtime()
    monkeypatch.setattr(media_api, "shared_video_runtime", fake)
    monkeypatch.setattr(media_api, "drone_video_link_connected", lambda: False)

    with pytest.raises(HTTPException) as exc_info:
        await media_api.mjpeg_proxy(SimpleNamespace(), user=object())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["reason"] == "Drone is not connected"
    assert fake.ensure_calls == 0


@pytest.mark.asyncio
async def test_start_video_stream_waits_for_drone_link(monkeypatch) -> None:
    class _Runtime(_FakeVideoRuntime):
        ensure_calls = 0
        source_calls = 0

        async def ensure_source_available(self) -> dict:
            self.source_calls += 1
            return {"status": "starting", "source": "udp://127.0.0.1:5600"}

        async def ensure_running(self) -> dict:
            self.ensure_calls += 1
            return await super().ensure_running()

    fake = _Runtime()
    monkeypatch.setattr(media_api, "shared_video_runtime", fake)
    monkeypatch.setattr(media_api, "drone_video_link_connected", lambda: False)

    result = await media_api.start_video_stream(user=object())

    assert result["status"] == "waiting_for_drone"
    assert result["retry_after_ms"] == 5000
    assert fake.source_calls == 0
    assert fake.ensure_calls == 0


@pytest.mark.asyncio
async def test_mjpeg_proxy_returns_503_when_camera_unavailable(monkeypatch) -> None:
    fake = _FakeVideoRuntime()
    monkeypatch.setattr(media_api, "shared_video_runtime", fake)
    monkeypatch.setattr(media_api, "drone_video_link_connected", lambda: True)

    with pytest.raises(HTTPException) as exc_info:
        await media_api.mjpeg_proxy(SimpleNamespace(), user=object())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["message"] == "Camera unavailable"


@pytest.mark.asyncio
async def test_mjpeg_proxy_honors_backoff_without_starting_worker(monkeypatch) -> None:
    class _BackoffRuntime(_FakeVideoRuntime):
        ensure_calls = 0

        async def readiness_status(self) -> dict:
            return {
                **await self.status(),
                "state": "unavailable",
                "retry_after_ms": 15000,
                "last_error": "Video stream in backoff",
            }

        async def ensure_running(self) -> dict:
            self.ensure_calls += 1
            return await super().ensure_running()

    fake = _BackoffRuntime()
    monkeypatch.setattr(media_api, "shared_video_runtime", fake)
    monkeypatch.setattr(media_api, "drone_video_link_connected", lambda: True)

    with pytest.raises(HTTPException) as exc_info:
        await media_api.mjpeg_proxy(SimpleNamespace(), user=object())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["retry_after_ms"] == 15000
    assert fake.ensure_calls == 0


@pytest.mark.asyncio
async def test_start_video_stream_honors_backoff_without_restarting(monkeypatch) -> None:
    class _BackoffRuntime(_FakeVideoRuntime):
        ensure_calls = 0
        source_calls = 0

        async def readiness_status(self) -> dict:
            return {
                **await self.status(),
                "state": "unavailable",
                "retry_after_ms": 15000,
                "last_error": "Video stream in backoff",
            }

        async def ensure_source_available(self) -> dict:
            self.source_calls += 1
            return {"status": "starting", "source": "udp://127.0.0.1:5600"}

        async def ensure_running(self) -> dict:
            self.ensure_calls += 1
            return await super().ensure_running()

    fake = _BackoffRuntime()
    monkeypatch.setattr(media_api, "shared_video_runtime", fake)
    monkeypatch.setattr(media_api, "drone_video_link_connected", lambda: True)

    result = await media_api.start_video_stream(user=object())

    assert result["status"] == "unavailable"
    assert result["retry_after_ms"] == 15000
    assert fake.source_calls == 0
    assert fake.ensure_calls == 0


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
