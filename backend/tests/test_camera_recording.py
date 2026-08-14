from __future__ import annotations

from unittest.mock import MagicMock, patch

import paramiko

from backend.infrastructure.camera import recording


def test_wait_for_stream_closes_response_on_success() -> None:
    response = MagicMock()
    response.status_code = 200
    response.close = MagicMock()

    with patch.object(recording.requests, "get", return_value=response) as get:
        assert recording.wait_for_stream("http://example/stream", timeout=1) is True
        get.assert_called_once()
        response.close.assert_called_once()


def test_mjpeg_stream_closes_response_when_iteration_stops() -> None:
    import numpy as np

    response = MagicMock()
    response.iter_content.return_value = iter([b"\xff\xd8\xff\xd9"])
    response.close = MagicMock()

    with patch.object(recording.requests, "get", return_value=response):
        with patch.object(recording.cv2, "imdecode", return_value=np.zeros((2, 2, 3), dtype=np.uint8)):
            frames = list(recording.mjpeg_stream("http://example/stream"))
        assert len(frames) == 1
        response.close.assert_called_once()


def test_mjpeg_stream_closes_response_when_generator_closed_early() -> None:
    import numpy as np

    response = MagicMock()
    response.iter_content.return_value = iter([b"\xff\xd8\xff\xd9", b"\xff\xd8\xff\xd9"])
    response.close = MagicMock()

    with patch.object(recording.requests, "get", return_value=response):
        with patch.object(recording.cv2, "imdecode", return_value=np.zeros((2, 2, 3), dtype=np.uint8)):
            generator = recording.mjpeg_stream("http://example/stream")
            next(generator)
            generator.close()
        response.close.assert_called_once()


def test_open_http_stream_uses_connect_and_read_timeouts() -> None:
    response = MagicMock()
    with patch.object(recording.requests, "get", return_value=response) as get:
        with recording._open_http_stream("http://example/stream", connect_timeout_s=1.5, read_timeout_s=9.0):
            pass
        get.assert_called_once_with(
            "http://example/stream",
            stream=True,
            timeout=(1.5, 9.0),
        )
        response.close.assert_called_once()


def test_configure_ssh_client_rejects_unknown_hosts_in_production(monkeypatch) -> None:
    monkeypatch.setattr(recording.settings, "app_env", "production")
    ssh = MagicMock()
    recording._configure_ssh_client(ssh)
    ssh.load_system_host_keys.assert_called_once()
    policy = ssh.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, paramiko.RejectPolicy)


def test_configure_ssh_client_allows_auto_add_in_local(monkeypatch) -> None:
    monkeypatch.setattr(recording.settings, "app_env", "local")
    ssh = MagicMock()
    recording._configure_ssh_client(ssh)
    policy = ssh.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, paramiko.AutoAddPolicy)
