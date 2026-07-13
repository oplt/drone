"""Event-loop-safe adapter for the blocking vehicle runtime port."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.infrastructure.runtime.blocking import run_blocking

from .types import Coordinate, EnuCoordinate, LocalCoordinate, Telemetry
from .vehicle_port import DroneClient


class AsyncDronePort:
    """Mandatory async boundary around the synchronous MAVLink client.

    Vehicle SDK calls can block on serial/network I/O and device sleeps. Keeping
    this adapter explicit prevents routes and use cases from scattering
    ``to_thread`` calls with inconsistent timeouts.
    """

    def __init__(self, drone: DroneClient) -> None:
        self._drone = drone

    @property
    def vehicle(self) -> Any:
        return getattr(self._drone, "vehicle", None)

    @property
    def home_location(self) -> Any:
        return self._drone.home_location

    async def _call(
        self,
        method: str,
        *args: Any,
        operation: str | None = None,
        timeout_s: float = 120.0,
        **kwargs: Any,
    ) -> Any:
        return await run_blocking(
            getattr(self._drone, method),
            *args,
            boundary="mavlink",
            operation=operation or method,
            call_timeout_s=timeout_s,
            **kwargs,
        )

    async def optional_call(
        self,
        method: str,
        *args: Any,
        operation: str | None = None,
        timeout_s: float = 120.0,
        **kwargs: Any,
    ) -> Any:
        """Invoke an optional adapter hook through the same MAVLink boundary."""
        if not callable(getattr(self._drone, method, None)):
            return None
        return await self._call(
            method,
            *args,
            operation=operation or f"vehicle_{method}",
            timeout_s=timeout_s,
            **kwargs,
        )

    async def connect(self, *, home_fallback_allowed: bool | None = None) -> None:
        await self._call(
            "connect",
            home_fallback_allowed=home_fallback_allowed,
            operation="vehicle_connect",
            timeout_s=90.0,
        )

    async def get_telemetry(self) -> Telemetry:
        return await self._call("get_telemetry", operation="vehicle_telemetry", timeout_s=15.0)

    async def arm_and_takeoff(self, alt: float) -> None:
        await self._call("arm_and_takeoff", alt, operation="vehicle_takeoff", timeout_s=180.0)

    async def goto(self, coord: Coordinate) -> None:
        await self._call("goto", coord, operation="vehicle_goto", timeout_s=120.0)

    async def set_mode(self, mode: str) -> None:
        await self._call("set_mode", mode, operation="vehicle_set_mode", timeout_s=30.0)

    async def follow_waypoints(self, path: Iterable[Coordinate]) -> None:
        await self._call(
            "follow_waypoints", path, operation="vehicle_follow_waypoints", timeout_s=1800.0
        )

    async def follow_local_setpoints(self, path: Iterable[LocalCoordinate]) -> None:
        await self._call(
            "follow_local_setpoints", path, operation="vehicle_follow_local", timeout_s=1800.0
        )

    async def follow_enu_setpoints(self, path: Iterable[EnuCoordinate]) -> None:
        await self._call(
            "follow_enu_setpoints", path, operation="vehicle_follow_enu", timeout_s=1800.0
        )

    async def land(self) -> None:
        await self._call("land", operation="vehicle_land", timeout_s=180.0)

    async def wait_until_disarmed(self, timeout_s: float = 900.0) -> None:
        await self._call(
            "wait_until_disarmed",
            timeout_s,
            operation="vehicle_wait_disarmed",
            timeout_s=timeout_s + 30.0,
        )

    async def set_groundspeed(self, speed_mps: float) -> bool:
        return await self._call("set_groundspeed", speed_mps, operation="vehicle_groundspeed")

    async def start_image_capture(
        self,
        *,
        mode: str = "distance",
        distance_m: float | None = None,
        interval_s: float | None = None,
    ) -> bool:
        return await self._call(
            "start_image_capture",
            mode=mode,
            distance_m=distance_m,
            interval_s=interval_s,
            operation="vehicle_capture_start",
        )

    async def stop_image_capture(self) -> bool:
        return await self._call("stop_image_capture", operation="vehicle_capture_stop")

    async def start_video_recording(self) -> bool:
        return bool(
            await self.optional_call("start_video_recording", operation="vehicle_video_start")
        )

    async def stop_video_recording(self) -> bool:
        return bool(
            await self.optional_call("stop_video_recording", operation="vehicle_video_stop")
        )

    async def send_velocity(
        self,
        vx: float,
        vy: float,
        vz: float,
        yaw_rate_dps: float = 0.0,
    ) -> None:
        await self._call(
            "send_velocity",
            vx,
            vy,
            vz,
            yaw_rate_dps,
            operation="vehicle_velocity",
            timeout_s=15.0,
        )

    async def pause_mission(self) -> bool:
        return await self._call("pause_mission", operation="vehicle_mission_pause", timeout_s=30.0)

    async def resume_mission(self) -> bool:
        return await self._call(
            "resume_mission", operation="vehicle_mission_resume", timeout_s=30.0
        )

    async def abort_mission(self) -> bool:
        return await self._call("abort_mission", operation="vehicle_mission_abort", timeout_s=30.0)

    async def download_captured_images(self, *, destination_dir: str) -> list[str]:
        return await self._call(
            "download_captured_images",
            destination_dir=destination_dir,
            operation="vehicle_download_images",
            timeout_s=900.0,
        )
