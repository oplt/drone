from __future__ import annotations

import shutil
import subprocess
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime import constants as runtime_constants
from backend.infrastructure.camera.stream_client import opencv_has_gstreamer

if TYPE_CHECKING:
    from backend.infrastructure.camera.runtime.shared_runtime import SharedVideoRuntime


def gazebo_subprocess_fallback_required() -> bool:
    """Use gst-launch when Gazebo UDP/RTP must be decoded outside OpenCV."""
    if not settings.drone_video_use_gazebo:
        return False
    source = (settings.drone_video_source_gazebo or "").strip().lower()
    if not source.startswith("udp://"):
        return False
    return not opencv_has_gstreamer()


def _get_gazebo_udp_port() -> int:
    source = settings.drone_video_source_gazebo
    parsed = urlparse(source)
    if parsed.scheme.lower() != "udp" or parsed.port is None:
        raise RuntimeError(f"Gazebo source must be udp://host:port (got: {source})")
    return parsed.port


def _discover_gazebo_enable_topics() -> list[str]:
    if shutil.which("gz") is None:
        return []
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True,
            text=True,
            timeout=4.0,
            check=True,
        )
    except Exception as exc:
        runtime_constants.logger.debug("Unable to list Gazebo topics via 'gz topic -l': %s", exc)
        return []

    topics: list[str] = []
    for line in result.stdout.splitlines():
        topic = line.strip()
        if not topic:
            continue
        if topic.endswith("/enable_streaming") and ("camera" in topic or "sensor" in topic):
            topics.append(topic)
    return topics


def _ensure_gazebo_streaming_enabled(runtime: 'SharedVideoRuntime | None' = None) -> None:
    now = time.monotonic()
    if now - runtime_constants._last_gazebo_enable_attempt < runtime_constants._GAZEBO_ENABLE_COOLDOWN_S:
        return
    runtime_constants._last_gazebo_enable_attempt = now

    topics = _discover_gazebo_enable_topics()
    if runtime is not None:
        runtime._gazebo_enable_topics = list(topics)

    if not topics:
        if not runtime_constants._gazebo_no_topic_warning_logged:
            runtime_constants.logger.warning("No Gazebo /enable_streaming topic discovered.")
            runtime_constants._gazebo_no_topic_warning_logged = True
        return

    enabled_any = False
    for topic in topics:
        try:
            subprocess.run(
                ["gz", "topic", "-t", topic, "-m", "gz.msgs.Boolean", "-p", "data: 1"],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=True,
            )
            runtime_constants.logger.info("Enabled Gazebo camera stream topic: %s", topic)
            enabled_any = True
        except Exception as exc:
            runtime_constants.logger.warning("Failed to enable Gazebo topic %s: %s", topic, exc)

    if runtime is not None and enabled_any:
        runtime._gazebo_streaming_enabled = True


def _gazebo_gst_mjpeg_command(udp_port: int) -> list[str]:
    return [
        "gst-launch-1.0",
        "-q",
        "udpsrc",
        f"port={udp_port}",
        "caps=application/x-rtp,media=(string)video,clock-rate=(int)90000,encoding-name=(string)H264,payload=(int)96",
        "!",
        "rtpjitterbuffer",
        "!",
        "rtph264depay",
        "!",
        "h264parse",
        "config-interval=-1",
        "!",
        "avdec_h264",
        "!",
        "videoconvert",
        "!",
        "jpegenc",
        "!",
        "multipartmux",
        "boundary=frame",
        "!",
        "fdsink",
        "fd=1",
    ]
