from __future__ import annotations

import importlib

import pytest


def _backend_media_available() -> bool:
    try:
        from pydantic import AliasChoices  # noqa: F401

        return True
    except ImportError:
        return False


def test_resolve_effective_decoder_prefers_seek_flag() -> None:
    decoders = importlib.import_module("backend.shared.media_frame_decoders")
    assert (
        decoders.resolve_effective_decoder(
            configured=decoders.DEFAULT_DECODER,
            decode_stride_enabled=True,
        )
        == "opencv_seek"
    )
    assert (
        decoders.resolve_effective_decoder(
            configured=decoders.DECODER_FFMPEG_PIPE,
            decode_stride_enabled=True,
        )
        == decoders.DECODER_FFMPEG_PIPE
    )


@pytest.mark.skipif(not _backend_media_available(), reason="backend runtime deps unavailable")
def test_decoder_modes_preserve_sample_indices_and_timestamps(tmp_path) -> None:
    import cv2
    import numpy as np

    from backend.shared.media_frames import iter_frames

    video = tmp_path / "decoder.avi"
    writer = cv2.VideoWriter(
        str(video),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (32, 24),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG writer is unavailable")
    for index in range(10):
        writer.write(np.full((24, 32, 3), index * 10, dtype=np.uint8))
    writer.release()

    baseline = list(iter_frames(video, every_seconds=0.3))
    seek = list(iter_frames(video, every_seconds=0.3, decode_stride_enabled=True))
    routed_seek = list(
        iter_frames(video, every_seconds=0.3, decoder_mode="opencv_seek")
    )

    expected_indices = [0, 3, 6, 9]
    assert [frame.frame_index for frame in baseline] == expected_indices
    assert [frame.frame_index for frame in seek] == expected_indices
    assert [frame.frame_index for frame in routed_seek] == expected_indices


@pytest.mark.skipif(not _backend_media_available(), reason="backend runtime deps unavailable")
def test_optional_decoder_falls_back_to_sequential(tmp_path) -> None:
    import cv2
    import numpy as np

    from backend.shared.media_frame_decoders import (
        DECODER_PYAV_SEQUENTIAL,
        iter_frames_with_decoder,
    )

    video = tmp_path / "fallback.avi"
    writer = cv2.VideoWriter(
        str(video),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (32, 24),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG writer is unavailable")
    writer.write(np.full((24, 32, 3), 10, dtype=np.uint8))
    writer.release()

    frames = list(
        iter_frames_with_decoder(
            video,
            every_seconds=1.0,
            decoder_mode=DECODER_PYAV_SEQUENTIAL,
        )
    )
    assert len(frames) >= 1


@pytest.mark.skipif(not _backend_media_available(), reason="backend runtime deps unavailable")
def test_corrupted_media_raises_for_default_decoder(tmp_path) -> None:
    from backend.shared.media_frames import iter_frames

    broken = tmp_path / "broken.avi"
    broken.write_bytes(b"not-a-video")

    with pytest.raises(ValueError, match="Could not open video"):
        list(iter_frames(broken, every_seconds=1.0))


@pytest.mark.skipif(not _backend_media_available(), reason="backend runtime deps unavailable")
def test_cancel_event_stops_sequential_decode(tmp_path) -> None:
    import threading

    import cv2
    import numpy as np

    from backend.shared.media_frames import iter_frames

    video = tmp_path / "cancel.avi"
    writer = cv2.VideoWriter(
        str(video),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (32, 24),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG writer is unavailable")
    for index in range(30):
        writer.write(np.full((24, 32, 3), index, dtype=np.uint8))
    writer.release()

    cancel_event = threading.Event()
    frames = []
    with pytest.raises(RuntimeError, match="cancelled"):
        for frame in iter_frames(
            video,
            every_seconds=0.1,
            cancel_event=cancel_event,
        ):
            frames.append(frame)
            cancel_event.set()

    assert len(frames) == 1
