from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import numpy as np

from backend.modules.patrol.vision.live_detections import LiveDetectionSampler
from backend.modules.patrol.vision.models import Detection, FramePacket


class _FakePersistence:
    def __init__(self) -> None:
        self.frames: list[int] = []

    async def persist_live_detections(self, *, detections, packet, telemetry, model_name) -> None:
        self.frames.append(packet.frame_id)


def _packet(frame_id: int, at: datetime) -> FramePacket:
    return FramePacket(frame_id=frame_id, ts=at, image=np.zeros((480, 640, 3), dtype=np.uint8))


def test_live_detections_publish_overlay_boxes_and_sample_storage() -> None:
    sampler = LiveDetectionSampler(0.5)
    persistence = _FakePersistence()
    at = datetime.utcnow()
    detections = [Detection(label="person", confidence=0.8, bbox=(10, 20, 30, 40))]

    asyncio.run(
        sampler.capture(
            detections=detections,
            packet=_packet(1, at),
            telemetry={},
            model_name="yolo26n.pt",
            persistence=persistence,
        )
    )
    asyncio.run(
        sampler.capture(
            detections=detections,
            packet=_packet(2, at + timedelta(seconds=0.1)),
            telemetry={},
            model_name="yolo26n.pt",
            persistence=persistence,
        )
    )

    assert sampler.current() == [
        {
            "label": "person",
            "confidence": 0.8,
            "bbox": [10, 20, 30, 40],
            "image_width": 640,
            "image_height": 480,
        }
    ]
    assert persistence.frames == [1]


def test_live_detections_clear_current_overlay_on_empty_frame() -> None:
    sampler = LiveDetectionSampler(0.5)

    asyncio.run(
        sampler.capture(
            detections=[],
            packet=_packet(1, datetime.utcnow()),
            telemetry={},
            model_name="yolo26n.pt",
            persistence=None,
        )
    )

    assert sampler.current() == []
