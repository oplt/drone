from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.modules.agriculture.contracts import MissionTelemetrySample
from backend.modules.agriculture.georeferencing import interpolate_pose


@dataclass(frozen=True)
class TelemetryMatch:
    lat: float | None
    lon: float | None
    altitude_m: float | None
    heading_deg: float | None
    quality: str = "unresolved"
    error_ms: float | None = None


class NearestTelemetryMatcher:
    """Repository-fed frame/pose matcher with explicit unresolved outcomes."""

    def __init__(
        self,
        mission_id: str | None,
        samples: Iterable[MissionTelemetrySample] | None = None,
        base_timestamp: datetime | None = None,
    ):
        self.mission_id = mission_id
        self.samples = list(samples or [])
        self.base_timestamp = base_timestamp

    def match(self, timestamp_seconds: float) -> TelemetryMatch:
        frame_time = (
            self.base_timestamp.astimezone(UTC) + timedelta(seconds=float(timestamp_seconds))
            if self.base_timestamp is not None
            else datetime.fromtimestamp(float(timestamp_seconds), tz=UTC)
        )
        result = interpolate_pose(self.samples, frame_time) if self.samples else None
        if result is not None and result.pose is not None:
            return TelemetryMatch(
                lat=result.pose.lat,
                lon=result.pose.lon,
                altitude_m=result.pose.altitude_m,
                heading_deg=result.pose.yaw_deg,
                quality=result.status,
                error_ms=result.error_ms,
            )
        return TelemetryMatch(
            lat=None,
            lon=None,
            altitude_m=None,
            heading_deg=None,
            quality=result.status if result is not None else "unresolved",
            error_ms=result.error_ms if result is not None else None,
        )
