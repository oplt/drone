from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.infrastructure.vehicle.frame_conversion import enu_to_local_ned
from backend.modules.vehicle_runtime.types import EnuCoordinate, LocalCoordinate


@dataclass(frozen=True)
class LocalPositionSample:
    north_m: float
    east_m: float
    down_m: float
    yaw_deg: float | None = None


class MavlinkLocalPositionAdapter:
    """Centralized ENU ↔ NED adapter for MAVLink LOCAL_POSITION setpoints."""

    def enu_path_to_local_ned(self, path: Iterable[EnuCoordinate]) -> list[LocalCoordinate]:
        converted: list[LocalCoordinate] = []
        for point in path:
            north, east, down = enu_to_local_ned(point.x_m, point.y_m, point.z_m)
            converted.append(
                LocalCoordinate(
                    north_m=float(north),
                    east_m=float(east),
                    down_m=float(down),
                    yaw_deg=point.yaw_deg,
                )
            )
        return converted

    def local_ned_to_enu(self, sample: LocalPositionSample) -> EnuCoordinate:
        return EnuCoordinate(
            x_m=float(sample.east_m),
            y_m=float(sample.north_m),
            z_m=float(-sample.down_m),
            yaw_deg=sample.yaw_deg,
        )
