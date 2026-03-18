import time
import os
from typing import Iterator, Union
import cv2
from datetime import datetime
import logging
import re
from functools import lru_cache
from backend.config import settings

logger = logging.getLogger(__name__)


def _is_rtsp(s: str) -> bool:
    return isinstance(s, str) and s.lower().startswith(
        ("rtsp://", "rtsps://", "udp://", "tcp://", "http://", "https://")
    )


def _get_udp_port(s: str) -> int | None:
    if isinstance(s, str) and s.lower().startswith("udp://"):
        match = re.search(r":(\d+)", s)
        if match:
            return int(match.group(1))
    return None


@lru_cache(maxsize=1)
def opencv_has_gstreamer() -> bool:
    """Return True when the active OpenCV build has GStreamer enabled."""
    try:
        info = cv2.getBuildInformation()
    except Exception:
        return False

    match = re.search(r"^\s*GStreamer:\s*(YES|NO)\s*$", info, re.MULTILINE)
    return bool(match and match.group(1).upper() == "YES")


class DroneVideoStream:
    """
    Enhanced video streaming for drone applications with:
      - Raspberry Pi 5 camera support (USB, CSI, network)
      - Auto backend selection (V4L2 for /dev/video*, FFMPEG for RTSP/HTTP/file)
      - GStreamer pipeline for raw UDP H264 streams (Gazebo)
      - Warm-up with retries and connection monitoring
      - Optional video recording with timestamp
      - Connection health monitoring
    """

    def __init__(
            self,
            source: Union[int, str, None] = 0,
            width: int = 640,
            height: int = 480,
            fps: int = 30,
            open_timeout_s: float = 5.0,
            probe_indices: int = 5,
            fallback_file: str | None = None,
            fps_limit: float | None = None,
            enable_recording: bool = False,
            recording_path: str = settings.drone_video_save_path,
            recording_format: str = "mp4",
    ):
        self.fps_limit = fps_limit
        self._last_ts = 0.0
        self.cap = None
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.enable_recording = enable_recording
        self.recording_path = recording_path
        self.recording_format = recording_format
        self.video_writer = None
        self.recording_filename = None
        self.connection_healthy = False
        self.last_frame_time = 0
        self.frame_count = 0

        if self.enable_recording:
            os.makedirs(self.recording_path, exist_ok=True)

        if source is not None:
            self.cap = self._open_source(source, width, height, fps, open_timeout_s)

        if self.cap is None and (source is None or isinstance(source, int)):
            for idx in range(0, probe_indices + 1):
                try:
                    self.cap = self._open_source(idx, width, height, fps, open_timeout_s)
                    logger.info(f"[Video] Probed working camera at index {idx}")
                    break
                except RuntimeError:
                    continue

        if self.cap is None and fallback_file and os.path.exists(fallback_file):
            try:
                self.cap = self._open_source(fallback_file, width, height, fps, open_timeout_s)
                logger.info(f"[Video] Using fallback file: {fallback_file}")
            except RuntimeError:
                pass

        if self.cap is None:
            raise RuntimeError(f"Camera not ready: source={source}")

        if self.enable_recording:
            self._start_recording()

    def _open_source(self, source, width, height, fps, open_timeout_s):
        udp_port = _get_udp_port(source)

        if udp_port is not None:
            if not opencv_has_gstreamer():
                raise RuntimeError(
                    "OpenCV was built without GStreamer support for UDP/RTP H264 sources"
                )

            gst_pipeline = (
                f"udpsrc port={udp_port} "
                "! application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264 "
                "! rtph264depay "
                "! avdec_h264 "
                "! videoconvert "
                "! appsink"
            )
            logger.info(f"Using GStreamer pipeline for UDP source: {gst_pipeline}")
            cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)

        elif isinstance(source, int):
            cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
            if not cap.isOpened():
                cap = cv2.VideoCapture(source)
        elif _is_rtsp(source) or isinstance(source, str):
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FPS, fps)
        else:
            cap = cv2.VideoCapture(source)

        if udp_port is None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)

        t0 = time.time()
        ok, _ = cap.read()
        while not ok and (time.time() - t0) < open_timeout_s:
            time.sleep(0.2)
            ok, _ = cap.read()
        if not ok:
            cap.release()
            raise RuntimeError(f"OpenCV source failed: {source}")

        self.connection_healthy = True
        return cap

    # --------- NEW public recording helpers (safe) ---------

    def recording_full_path(self) -> str | None:
        if not self.recording_filename:
            return None
        return os.path.join(self.recording_path, self.recording_filename)

    def start_recording(self) -> str | None:
        """Idempotent start. Returns filename if recording active."""
        if self.video_writer and self.video_writer.isOpened():
            return self.recording_filename
        self._start_recording()
        return self.recording_filename

    def stop_recording(self) -> str | None:
        """Idempotent stop. Returns filename that was recorded."""
        filename = self.recording_filename
        self._stop_recording()
        return filename

    # ------------------------------------------------------

    def _start_recording(self):
        if self.cap is None:
            return

        os.makedirs(self.recording_path, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.recording_filename = f"drone_video_{timestamp}.{self.recording_format}"
        full_path = os.path.join(self.recording_path, self.recording_filename)

        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or self.width
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self.height
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if actual_fps <= 0:
            actual_fps = self.fps

        if self.recording_format == "mp4":
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        elif self.recording_format == "avi":
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
        else:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        self.video_writer = cv2.VideoWriter(
            full_path, fourcc, actual_fps, (actual_width, actual_height)
        )

        if not self.video_writer.isOpened():
            logger.error(f"Failed to open video writer for {full_path}")
            self.video_writer = None
            self.recording_filename = None
        else:
            logger.info(f"Started video recording: {full_path}")

    def _stop_recording(self):
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            if self.recording_filename:
                logger.info(f"Stopped video recording: {self.recording_filename}")

    def _check_connection_health(self):
        if self.cap is None:
            self.connection_healthy = False
            return False

        ok, _ = self.cap.read()
        if not ok:
            self.connection_healthy = False
            logging.warning("Video stream connection lost")
            return False

        now = time.time()
        if self.last_frame_time > 0:
            frame_interval = now - self.last_frame_time
            expected_interval = 1.0 / self.fps
            if frame_interval > expected_interval * 2:
                logging.warning(
                    f"Video stream frame rate degraded: {1.0 / frame_interval:.1f} fps"
                )

        self.last_frame_time = now
        self.connection_healthy = True
        return True

    def frames(self) -> Iterator[tuple[int, any]]:
        while True:
            if self.frame_count % 30 == 0:
                if not self._check_connection_health():
                    logger.error("Video stream unhealthy, reconnecting...")
                    self._reconnect()
                    if self.cap is None:
                        break
                    continue

            ok, frame = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                if not ok:
                    logger.error("Failed to read frame from video source")
                    break

            if self.video_writer and self.video_writer.isOpened():
                self.video_writer.write(frame)

            if self.fps_limit:
                now = time.time()
                min_dt = 1.0 / float(self.fps_limit)
                if now - self._last_ts < min_dt:
                    time.sleep(min_dt - (now - self._last_ts))
                self._last_ts = time.time()

            self.frame_count += 1
            yield frame.shape[1], frame

    def _reconnect(self):
        try:
            if self.cap:
                self.cap.release()
            time.sleep(1.0)
            self.cap = self._open_source(self.source, self.width, self.height, self.fps, 5.0)
            if self.cap and self.cap.isOpened():
                logger.info("Reconnected to video source")
                if self.enable_recording:
                    self._start_recording()
            else:
                logger.error("Failed to reconnect to video source")
        except Exception as e:
            logger.error(f"Error during video reconnection: {e}")

    def get_connection_status(self) -> dict:
        return {
            "healthy": self.connection_healthy,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "resolution": f"{self.width}x{self.height}",
            "recording": self.video_writer is not None and self.video_writer.isOpened(),
            "recording_file": self.recording_filename,
        }

    def close(self):
        try:
            self._stop_recording()
            if self.cap:
                self.cap.release()
        except Exception as e:
            logger.error(f"Error closing video stream: {e}")


VideoStream = DroneVideoStream