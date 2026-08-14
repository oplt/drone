
from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime.constants import logger
from backend.infrastructure.camera.runtime.source_helpers import (
    _recording_filename,
    _recording_root_from_path,
)


class RuntimeRecordingMixin:
    """DroneKit and Gazebo fallback recording."""

    def _start_fallback_recording_locked(self, *, recording_root: Path) -> tuple[str, str]:
        writer = self._fallback_video_writer
        if writer is not None and writer.isOpened():
            return (
                self._fallback_recording_filename or "",
                self._fallback_recording_path or "",
            )

        latest_frame = self._latest_frame
        if latest_frame is None:
            raise RuntimeError("No video frame is available for Gazebo recording yet.")

        frame = cv2.imdecode(np.frombuffer(latest_frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("Failed to decode current Gazebo video frame.")

        filename = _recording_filename("mp4")
        full_path = recording_root / filename
        fps = max(1.0, float(settings.drone_video_fps or 30))
        writer = cv2.VideoWriter(
            str(full_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (int(frame.shape[1]), int(frame.shape[0])),
        )
        if not writer.isOpened():
            writer.release()
            raise RuntimeError(f"Failed to open video writer for {full_path}")

        writer.write(frame)
        self._fallback_video_writer = writer
        self._fallback_recording_filename = filename
        self._fallback_recording_path = str(full_path)
        logger.info("Started Gazebo fallback recording: %s", full_path)
        return filename, str(full_path)

    def _stop_fallback_recording_locked(self) -> tuple[str | None, str | None]:
        filename = self._fallback_recording_filename
        full_path = self._fallback_recording_path
        writer = self._fallback_video_writer
        self._fallback_video_writer = None
        if writer is not None:
            writer.release()
            if full_path:
                logger.info("Stopped Gazebo fallback recording: %s", full_path)
        return filename, full_path
    async def start_recording(self, *, recording_path: str | None = None) -> dict[str, Any]:

        await self.ensure_running()
        recording_root = _recording_root_from_path(recording_path)

        async with self._lock:
            if self._video is not None:
                self._video.recording_path = str(recording_root)
                filename = self._video.start_recording()
                full_path = self._video.recording_full_path()
            else:
                filename, full_path = self._start_fallback_recording_locked(
                    recording_root=recording_root
                )

        status = await self.status()
        status.update(
            {
                "recording": bool(filename),
                "recording_file": filename,
                "recording_path": full_path,
            }
        )
        return status

    async def stop_recording(self) -> dict[str, Any]:
        async with self._lock:
            if self._video is not None:
                full_path = self._video.recording_full_path()
                filename = self._video.stop_recording()
            else:
                filename, full_path = self._stop_fallback_recording_locked()
                if filename is None and full_path is None:
                    return {
                        "recording": False,
                        "recording_file": None,
                        "recording_path": None,
                    }

        status = await self.status()
        status.update(
            {
                "recording": False,
                "recording_file": filename,
                "recording_path": full_path,
            }
        )
        return status

