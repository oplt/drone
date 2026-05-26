from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from backend.modules.patrol.vision.models import Detection, FramePacket


class LiveDetectionPersistence(Protocol):
    async def persist_live_detections(
        self,
        *,
        detections: list[Detection],
        packet: FramePacket,
        telemetry: dict[str, Any],
        model_name: str,
    ) -> None: ...


class LiveDetectionSampler:
    def __init__(self, persist_interval_s: float) -> None:
        self.persist_interval_s = persist_interval_s
        self._current: list[dict[str, Any]] = []
        self._last_persisted_at: datetime | None = None

    def reset(self) -> None:
        self._current = []
        self._last_persisted_at = None

    def current(self) -> list[dict[str, Any]]:
        return self._current

    async def capture(
        self,
        *,
        detections: list[Detection],
        packet: FramePacket,
        telemetry: dict[str, Any],
        model_name: str,
        persistence: LiveDetectionPersistence | None,
    ) -> None:
        image_height, image_width = packet.image.shape[:2]
        self._current = [
            {
                "label": detection.label,
                "confidence": detection.confidence,
                "bbox": list(detection.bbox),
                "image_width": int(image_width),
                "image_height": int(image_height),
            }
            for detection in detections
        ]
        due = (
            self._last_persisted_at is None
            or (packet.ts - self._last_persisted_at).total_seconds() >= self.persist_interval_s
        )
        if persistence is None or not detections or not due:
            return
        await persistence.persist_live_detections(
            detections=detections,
            packet=packet,
            telemetry=telemetry,
            model_name=model_name,
        )
        self._last_persisted_at = packet.ts
