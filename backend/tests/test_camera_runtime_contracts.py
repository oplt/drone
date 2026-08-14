from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime import (
    SharedVideoRuntime,
    drone_video_link_connected,
)
from backend.infrastructure.camera.runtime.gazebo import gazebo_subprocess_fallback_required
from backend.infrastructure.camera.runtime.shutdown import (
    _is_benign_shutdown_error,
    _is_benign_shutdown_exit_code,
)


def test_shared_video_runtime_source_url_uses_pi_feed_when_not_gazebo(monkeypatch) -> None:
    monkeypatch.setattr(settings, "drone_video_use_gazebo", False)
    monkeypatch.setattr(settings, "raspberry_ip", "192.168.1.50")

    runtime = SharedVideoRuntime()

    assert runtime.source_url() == "http://192.168.1.50:5000/video_feed"


def test_shared_video_runtime_source_url_uses_gazebo_source(monkeypatch) -> None:
    monkeypatch.setattr(settings, "drone_video_use_gazebo", True)
    monkeypatch.setattr(settings, "drone_video_source_gazebo", "udp://127.0.0.1:5600")

    runtime = SharedVideoRuntime()

    assert runtime.source_url() == "udp://127.0.0.1:5600"


@pytest.mark.parametrize("code", [0, -2, -15, 130, 143])
def test_benign_shutdown_exit_codes(code: int) -> None:
    assert _is_benign_shutdown_exit_code(code) is True


def test_non_benign_shutdown_exit_code() -> None:
    assert _is_benign_shutdown_exit_code(1) is False
    assert _is_benign_shutdown_exit_code(None) is False


def test_benign_shutdown_error_detects_cancel_and_signal_codes() -> None:
    assert _is_benign_shutdown_error(asyncio.CancelledError()) is True
    assert _is_benign_shutdown_error(RuntimeError("process exited with code -15")) is True
    assert _is_benign_shutdown_error(RuntimeError("ExternalShutdownException")) is True
    assert _is_benign_shutdown_error(RuntimeError("camera unplugged")) is False


def test_gazebo_subprocess_fallback_required_for_udp_without_gstreamer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "drone_video_use_gazebo", True)
    monkeypatch.setattr(settings, "drone_video_source_gazebo", "udp://127.0.0.1:5600")
    monkeypatch.setattr(
        "backend.infrastructure.camera.runtime.gazebo.opencv_has_gstreamer",
        lambda: False,
    )

    assert gazebo_subprocess_fallback_required() is True


def test_gazebo_subprocess_fallback_not_required_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "drone_video_use_gazebo", False)

    assert gazebo_subprocess_fallback_required() is False


def test_drone_video_link_connected_reads_telemetry_snapshot(monkeypatch) -> None:
    snapshot = {"source_connected": True}
    manager = SimpleNamespace(runtime_snapshot=MagicMock(return_value=snapshot))
    monkeypatch.setattr(
        "backend.infrastructure.camera.runtime.link.telemetry_manager",
        manager,
    )

    assert drone_video_link_connected() is True
    manager.runtime_snapshot.assert_called_once()
