from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryMatch:
    lat: float | None
    lon: float | None
    altitude_m: float | None
    heading_deg: float | None


class NearestTelemetryMatcher:
    """Placeholder adapter for matching a frame timestamp to mission telemetry.

    Connect this to modules.telemetry.repository later. Keep it outside detector
    logic so CV inference remains testable without MAVLink/DB dependencies.
    """

    def __init__(self, mission_id: str | None):
        self.mission_id = mission_id

    def match(self, timestamp_seconds: float) -> TelemetryMatch:
        # TODO: query telemetry by mission_id and interpolate nearest MAVLink event.
        # Return empty for first MVP if video files have no telemetry timestamps yet.
        return TelemetryMatch(
            lat=None,
            lon=None,
            altitude_m=None,
            heading_deg=None,
        )
