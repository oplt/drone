from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class FramePacket:
    frame_id: int
    ts: datetime
    image: Any


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass
class Track:
    track_id: int
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    age_frames: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeoPoint:
    lat: float
    lon: float
    alt: float | None = None


@dataclass
class AnomalyEvent:
    event_type: str
    confidence: float
    location: GeoPoint | None
    payload: dict[str, Any]
