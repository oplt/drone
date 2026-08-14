"""Compatibility exports for shared media frame decoding."""

from backend.shared.media_frames import (
    ExtractedFrame,
    VideoMetadata,
    async_iter_frames,
    frame_timestamp_seconds,
    iter_frames,
    read_video_metadata,
    read_video_metadata_async,
    sampled_frame_indices,
)

__all__ = [
    "ExtractedFrame",
    "VideoMetadata",
    "async_iter_frames",
    "frame_timestamp_seconds",
    "iter_frames",
    "read_video_metadata",
    "read_video_metadata_async",
    "sampled_frame_indices",
]
