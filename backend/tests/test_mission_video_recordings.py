from __future__ import annotations

from pathlib import Path

from backend.modules.video_analysis.mission_recordings import _resolve_recording_path


def test_resolve_recording_path_prefers_absolute_path(tmp_path: Path) -> None:
    video = tmp_path / "flight.mp4"
    video.write_bytes(b"fake")

    resolved = _resolve_recording_path(str(video), None)

    assert resolved == video.resolve()


def test_resolve_recording_path_falls_back_to_filename(tmp_path: Path, monkeypatch) -> None:
    from backend.core.config import runtime as runtime_module

    monkeypatch.setattr(runtime_module.settings, "drone_video_save_path", str(tmp_path))
    video = tmp_path / "drone_video_20260101_120000.mp4"
    video.write_bytes(b"fake")

    resolved = _resolve_recording_path(None, video.name)

    assert resolved == video.resolve()
