"""Bounded low-latency advisory processing primitives for live agriculture view."""

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable
from queue import Full, Queue

import cv2
import numpy as np

from backend.modules.agriculture.heuristics import segment_rgb_crop_soil_water, visible_water_heuristic
from backend.modules.agriculture.quality import compute_frame_quality


@dataclass(frozen=True)
class LiveFrame:
    frame_index: int
    timestamp_seconds: float
    image: Any
    received_at: float


@dataclass(frozen=True)
class LiveAdvisory:
    frame_index: int
    timestamp_seconds: float
    state: str
    alerts: tuple[str, ...]
    geolocation: dict[str, float] | None
    expires_at: float


class LiveAgricultureProcessor:
    """Drop-oldest bounded queue; post-flight pipeline remains authoritative."""

    def __init__(self, *, max_queue: int = 8, stale_after_s: float = 5.0, sampler_hz: float = 3.0) -> None:
        self.queue: Queue[LiveFrame] = Queue(maxsize=max(1, max_queue))
        self.stale_after_s = max(1.0, stale_after_s)
        self.sampler_hz = max(2.0, min(5.0, sampler_hz))
        self.dropped_frames = 0

    def submit(self, frame: LiveFrame) -> bool:
        try:
            self.queue.put_nowait(frame)
            return True
        except Full:
            try: self.queue.get_nowait()
            except Exception: pass
            self.dropped_frames += 1
            self.queue.put_nowait(frame)
            return False

    def process_one(self, infer: Callable[[Any], LiveAdvisory], *, now: float | None = None) -> LiveAdvisory | None:
        try: frame = self.queue.get_nowait()
        except Exception: return None
        current = monotonic() if now is None else now
        if current - frame.received_at > self.stale_after_s:
            return LiveAdvisory(frame.frame_index, frame.timestamp_seconds, "stale", ("stale_frame",), None, current)
        result = infer(frame.image)
        return result if result.expires_at > current else LiveAdvisory(frame.frame_index, frame.timestamp_seconds, "stale", ("stale_result",), result.geolocation, current)

    @staticmethod
    def rgb_advisory(image_bgr: Any, *, frame_index: int, timestamp_seconds: float, geolocation: dict[str, float] | None = None) -> LiveAdvisory:
        quality = compute_frame_quality(image_bgr)
        segmentation = segment_rgb_crop_soil_water(image_bgr)
        water = visible_water_heuristic(segmentation, quality.metrics)
        alerts = list(quality.reasons)
        if water.get("status") == "candidate": alerts.append("large_visible_water_region")
        if water.get("status") == "uncertain": alerts.append("water_quality_uncertain")
        return LiveAdvisory(frame_index, timestamp_seconds, quality.state, tuple(sorted(set(alerts))), geolocation, monotonic() + 5.0)


def decode_rgb_frame(content: bytes, *, max_bytes: int = 12_000_000) -> np.ndarray:
    if not content or len(content) > max_bytes:
        raise ValueError("live frame is empty or exceeds the 12 MB limit")
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("live frame is not a decodable RGB image")
    return image
