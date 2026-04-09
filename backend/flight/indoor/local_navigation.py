from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.drone.models import LocalCoordinate

from .enums import IndoorFrame
from .models import DockingTarget, LocalPose
from .slam import SimulatedSLAMProvider, SLAMProvider


class LocalNavigationAdapter(Protocol):
    async def arm_and_takeoff_local(self, hover_alt_m: float) -> None: ...

    async def goto_local_pose(
        self,
        pose: LocalPose,
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None: ...

    async def follow_local_path(
        self,
        path: Sequence[LocalPose],
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None: ...

    async def hold_position(self, *, timeout_s: float = 1.0) -> None: ...

    async def land_on_dock(self, target: DockingTarget | None = None) -> None: ...

    async def safe_land(self) -> None: ...

    async def wait_until_disarmed(self, timeout_s: float = 900.0) -> None: ...


@dataclass
class DroneLocalNavigationAdapter:
    drone: object
    slam_provider: SLAMProvider

    async def arm_and_takeoff_local(self, hover_alt_m: float) -> None:
        await asyncio.to_thread(self.drone.arm_and_takeoff, float(hover_alt_m))

    async def goto_local_pose(
        self,
        pose: LocalPose,
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        await self.follow_local_path([pose], speed_mps=speed_mps, timeout_s=timeout_s)

    async def follow_local_path(
        self,
        path: Sequence[LocalPose],
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        del timeout_s
        if not path:
            return
        if speed_mps is not None:
            for name in ("set_groundspeed", "set_speed", "set_cruise_speed"):
                setter = getattr(self.drone, name, None)
                if not callable(setter):
                    continue
                try:
                    await asyncio.to_thread(setter, float(speed_mps))
                    break
                except Exception:
                    continue

        control_path: list[LocalCoordinate] = []
        for pose in path:
            resolved = await self.slam_provider.to_control_frame(
                pose,
                frame_id=IndoorFrame.ODOM.value,
            )
            control_path.append(
                LocalCoordinate(
                    north_m=float(resolved.y_m),
                    east_m=float(resolved.x_m),
                    down_m=-float(resolved.z_m),
                    yaw_deg=resolved.yaw_deg,
                )
            )
        await asyncio.to_thread(self.drone.follow_local_setpoints, control_path)

    async def hold_position(self, *, timeout_s: float = 1.0) -> None:
        hold_fn = getattr(self.drone, "hold_position", None)
        if callable(hold_fn):
            try:
                await asyncio.to_thread(hold_fn)
                await asyncio.sleep(float(timeout_s))
                return
            except Exception:
                pass
        await asyncio.to_thread(self.drone.set_mode, "LOITER")
        await asyncio.sleep(float(timeout_s))

    async def land_on_dock(self, target: DockingTarget | None = None) -> None:
        land_fn = getattr(self.drone, "land_on_dock", None)
        if callable(land_fn):
            try:
                await asyncio.to_thread(land_fn, target)
                return
            except TypeError:
                await asyncio.to_thread(land_fn)
                return
            except Exception:
                pass
        await asyncio.to_thread(self.drone.land)

    async def safe_land(self) -> None:
        await asyncio.to_thread(self.drone.land)

    async def wait_until_disarmed(self, timeout_s: float = 900.0) -> None:
        wait_fn = getattr(self.drone, "wait_until_disarmed", None)
        if callable(wait_fn):
            await asyncio.to_thread(wait_fn, float(timeout_s))


@dataclass
class SimulatedLocalNavigationAdapter:
    slam_provider: SimulatedSLAMProvider

    async def arm_and_takeoff_local(self, hover_alt_m: float) -> None:
        current = await self.slam_provider.get_pose()
        self.slam_provider.move_along(
            [current.translated(dz_m=float(hover_alt_m) - float(current.z_m))]
        )

    async def goto_local_pose(
        self,
        pose: LocalPose,
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        del speed_mps, timeout_s
        resolved = await self.slam_provider.to_control_frame(pose, frame_id=IndoorFrame.MAP.value)
        self.slam_provider.move_along([resolved])

    async def follow_local_path(
        self,
        path: Sequence[LocalPose],
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        del speed_mps, timeout_s
        resolved: list[LocalPose] = []
        for pose in path:
            resolved.append(
                await self.slam_provider.to_control_frame(
                    pose,
                    frame_id=IndoorFrame.MAP.value,
                )
            )
        self.slam_provider.move_along(resolved)

    async def hold_position(self, *, timeout_s: float = 1.0) -> None:
        await asyncio.sleep(float(timeout_s))

    async def land_on_dock(self, target: DockingTarget | None = None) -> None:
        del target
        current = await self.slam_provider.get_pose()
        self.slam_provider.move_along([current.translated(dz_m=-float(current.z_m))])

    async def safe_land(self) -> None:
        await self.land_on_dock(None)

    async def wait_until_disarmed(self, timeout_s: float = 900.0) -> None:
        del timeout_s
