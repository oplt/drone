from __future__ import annotations

from backend.infrastructure.camera.runtime.runtime_core import RuntimeCoreMixin
from backend.infrastructure.camera.runtime.runtime_frames import RuntimeFramesMixin
from backend.infrastructure.camera.runtime.runtime_lifecycle import RuntimeLifecycleMixin
from backend.infrastructure.camera.runtime.runtime_recording import RuntimeRecordingMixin
from backend.infrastructure.camera.runtime.runtime_source import RuntimeSourceMixin
from backend.infrastructure.camera.runtime.runtime_worker import RuntimeWorkerMixin


class SharedVideoRuntime(
    RuntimeCoreMixin,
    RuntimeSourceMixin,
    RuntimeLifecycleMixin,
    RuntimeFramesMixin,
    RuntimeWorkerMixin,
    RuntimeRecordingMixin,
):
    """Process-wide shared MJPEG video runtime for drone camera feeds."""


shared_video_runtime = SharedVideoRuntime()
