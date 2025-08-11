# core/stream.py
import time
import os
from typing import Iterator, Union
import cv2

def _is_rtsp(s: str) -> bool:
    return isinstance(s, str) and s.lower().startswith(("rtsp://", "rtsps://", "udp://", "tcp://", "http://", "https://"))

class VideoStream:
    """
    Robust OpenCV capture with:
      - auto backend selection (V4L2 for /dev/video*, FFMPEG for RTSP/HTTP/file)
      - warm-up with retries
      - multi-source probing (0..5) when an int source fails
      - optional fallback file when live source is unavailable
    """
    def __init__(
            self,
            source: Union[int, str, None] = 0,
            width: int = 640,
            height: int = 480,
            open_timeout_s: float = 5.0,
            probe_indices: int = 5,
            fallback_file: str | None = None,
            fps_limit: float | None = 1.0,  # throttle frame rate to save CPU/LLM cost (None = no limit)
    ):
        self.fps_limit = fps_limit
        self._last_ts = 0.0
        self.cap = None

        # 1) Try the requested source
        if source is not None:
            self.cap = self._open_source(source, width, height, open_timeout_s)

        # 2) If that failed AND we were given an int (or None), probe other /dev/videoN
        if self.cap is None and (source is None or isinstance(source, int)):
            for idx in range(0, probe_indices + 1):
                try:
                    self.cap = self._open_source(idx, width, height, open_timeout_s)
                    print(f"[Video] Probed working camera at index {idx}")
                    break
                except RuntimeError:
                    continue

        # 3) If still no live source, try fallback file if provided
        if self.cap is None and fallback_file and os.path.exists(fallback_file):
            try:
                self.cap = self._open_source(fallback_file, width, height, open_timeout_s)
                print(f"[Video] Using fallback file: {fallback_file}")
            except RuntimeError:
                pass

        if self.cap is None:
            raise RuntimeError(f"Camera not ready: source={source}")

    def _open_source(self, source, width, height, open_timeout_s):
        if isinstance(source, int):
            cap = cv2.VideoCapture(source, cv2.CAP_V4L2)  # Linux USB cam
        elif _is_rtsp(source) or isinstance(source, str):
            # Prefer FFMPEG backend for RTSP/HTTP/file
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            # Helpful FFmpeg options for low-latency RTSP (ignored if not RTSP)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FPS, 30)
        else:
            cap = cv2.VideoCapture(source)

        # Try to set resolution (may be ignored by RTSP)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        # Warm-up / readiness check
        t0 = time.time()
        ok, _ = cap.read()
        while not ok and (time.time() - t0) < open_timeout_s:
            time.sleep(0.2)
            ok, _ = cap.read()
        if not ok:
            cap.release()
            raise RuntimeError(f"OpenCV source failed: {source}")
        return cap

    def frames(self) -> Iterator[tuple[int, any]]:
        while True:
            ok, frame = self.cap.read()
            if not ok:
                # For files, try to loop from start
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                if not ok:
                    break

            # FPS throttle
            if self.fps_limit:
                now = time.time()
                min_dt = 1.0 / float(self.fps_limit)
                if now - self._last_ts < min_dt:
                    # Busy-wait light sleep to avoid extra CPU
                    time.sleep(min_dt - (now - self._last_ts))
                self._last_ts = time.time()

            yield frame.shape[1], frame  # (width, frame)

    def close(self):
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
