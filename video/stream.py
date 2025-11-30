import time
import logging
from typing import Iterator, Tuple, Optional
import requests
import paramiko
import cv2
import numpy as np
from config import settings


class RaspberryClient:
    """
    Class-based version of pc_view_stream.py.
    Handles:
        - SSH: start camera script on Raspberry Pi
        - Polling /video_feed until ready
        - MJPEG frame streaming (via HTTP)
        - Yields frames identical to DroneVideoStream.frames()
    """

    def __init__(
            self,
            host: Optional[str] = None,
            user: Optional[str] = None,
            ssh_key: Optional[str] = None,
            script_path: Optional[str] = None,
            port: Optional[int] = None,
            timeout: int = 40
    ):
        self.host = host or settings.rasperry_ip
        self.user = user or settings.rasperry_user
        self.ssh_key = ssh_key or settings.ssh_key_path
        self.script_path = script_path or settings.rasperry_streaming_script_path
        self.port = port or settings.rasperry_port

        self.stream_url = f"http://{self.host}:{self.port}/video_feed"
        self.timeout = timeout

        self._ssh_client = None
        self._resp = None
        self._running = False

        # health / stats
        self._frame_count = 0
        self._last_frame_time = None
        self._last_resolution = None
        self._start_time = None
        self._recording = False
        self._recording_file = None


    def set_recording_file(self, path: str):
        self._recording_file = path

    # ---------------------------------------------------------
    # SSH functions
    # ---------------------------------------------------------

    def _connect_ssh(self):
        if self._ssh_client:
            return

        logging.info(f"[RaspiCam] SSH connecting to {self.host} as {self.user}")
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            username=self.user,
            key_filename=self.ssh_key,
            timeout=10,
        )
        self._ssh_client = client

    def _start_remote_script(self):
        """Starts the Raspberry Pi camera server using SSH."""
        self._connect_ssh()

        cmd = (
            f"nohup python3 {self.script_path} "
            "> /tmp/pi_cam_server.log 2>&1 &"
        )

        logging.info(f"[RaspiCam] Starting remote camera: {cmd}")
        self._ssh_client.exec_command(cmd)
        logging.info("[RaspiCam] Remote camera server started")

    def _wait_for_stream(self) -> bool:
        """Wait for HTTP 200 OK from the MJPEG server."""
        logging.info(f"[RaspiCam] Waiting for stream at {self.stream_url} ...")
        start = time.time()

        while time.time() - start < self.timeout:
            try:
                r = requests.get(self.stream_url, stream=True, timeout=3)
                if r.status_code == 200:
                    r.close()
                    logging.info("[RaspiCam] Stream is up!")
                    return True
            except:
                pass

            logging.info("[RaspiCam] Stream not ready, retrying...")
            time.sleep(2)

        logging.error("[RaspiCam] Stream did not become ready in time")
        return False

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def start(self):
        """Start remote server + wait until stream is accessible."""
        if self._running:
            return

        self._start_remote_script()

        if not self._wait_for_stream():
            raise RuntimeError("MJPEG stream failed to start")

        self._running = True
        self._start_time = time.time()
        self._frame_count = 0
        self._last_frame_time = None
        self._last_resolution = None

    def frames(self) -> Iterator[Tuple[int, np.ndarray]]:
        """
        Yield frames as (width, frame) to match DroneVideoStream interface.
        """

        if not self._running:
            self.start()

        logging.info(f"[RaspiCam] Opening HTTP MJPEG stream from {self.stream_url}")
        self._resp = requests.get(self.stream_url, stream=True)
        buffer = b""

        try:
            for chunk in self._resp.iter_content(chunk_size=1024):
                if not chunk:
                    continue
                buffer += chunk

                a = buffer.find(b"\xff\xd8")
                b = buffer.find(b"\xff\xd9")

                if a != -1 and b != -1 and b > a:
                    jpg = buffer[a:b+2]
                    buffer = buffer[b+2:]

                    frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        h, w = frame.shape[:2]
                        self._frame_count += 1
                        self._last_frame_time = time.time()
                        self._last_resolution = (w, h)
                        yield w, frame

        finally:
            logging.info("[RaspiCam] Closing MJPEG stream")
            self._cleanup()

    def stop(self):
        """Stop all connections."""
        self._running = False
        self._cleanup()

    def close(self):
        self.stop()

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    def _cleanup(self):
        if self._resp:
            try:
                self._resp.close()
            except:
                pass
            self._resp = None

        if self._ssh_client:
            try:
                self._ssh_client.close()
            except:
                pass
            self._ssh_client = None

        logging.info("[RaspiCam] Cleaned up SSH + HTTP stream")


    def get_connection_status(self):
        """Return a simple health snapshot for the video stream."""
        now = time.time()
        # consider healthy if frames arriving recently
        healthy = (
                self._running and
                self._last_frame_time is not None and
                (now - self._last_frame_time) < 5.0  # 5s without frames => unhealthy
        )

        fps = 0.0
        if self._start_time and self._frame_count > 0:
            fps = self._frame_count / max(1e-3, (now - self._start_time))

        return {
            "healthy": healthy,
            "frame_count": self._frame_count,
            "fps": fps,
            "resolution": self._last_resolution,
            "recording": self._recording,
            "recording_file": self._recording_file,
            "connected": self._running,
            "stream_url": self.stream_url,
        }


