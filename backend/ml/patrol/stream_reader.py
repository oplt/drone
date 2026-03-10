from __future__ import annotations

import cv2
import time
from datetime import datetime
from typing import Optional

from backend.ml.patrol.models import FramePacket


class StreamReader:
    """
    Blocking OpenCV reader.

    Important:
    - This class is intentionally synchronous.
    - Call read() via asyncio.to_thread(...) from async code.
    """

    def __init__(self, source: str | int, frame_stride: int = 1, reopen_delay_s: float = 0.2):
        self.source = source
        self.frame_stride = max(1, int(frame_stride))
        self.reopen_delay_s = max(0.01, float(reopen_delay_s))

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_id = 0
        self._raw_id = 0
        self._opened = False

    def open(self) -> None:
        if self._cap is not None and self._cap.isOpened():
            self._opened = True
            return

        source = self.source
        if isinstance(source, str):
            stripped = source.strip()
            if stripped.isdigit():
                source = int(stripped)

        self._cap = cv2.VideoCapture(source)
        self._opened = bool(self._cap and self._cap.isOpened())
        if not self._opened:
            raise RuntimeError(f"Cannot open stream: {self.source}")

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None
        self._opened = False

    def read(self) -> Optional[FramePacket]:
        """
        Blocking read.

        Returns:
            FramePacket when a valid frame passes stride filtering.
            None when no frame is currently available.
        """
        if not self._opened or self._cap is None:
            self.open()

        assert self._cap is not None

        ok, frame = self._cap.read()
        if not ok:
            # best-effort reconnect path
            self.close()
            time.sleep(self.reopen_delay_s)
            try:
                self.open()
            except Exception:
                return None
            return None

        self._raw_id += 1
        if self._raw_id % self.frame_stride != 0:
            return None

        packet = FramePacket(
            frame_id=self._frame_id,
            ts=datetime.utcnow(),
            image=frame,
        )
        self._frame_id += 1
        return packet
