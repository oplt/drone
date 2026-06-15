from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

try:
    from backend.modules.vehicle_runtime.types import LocalCoordinate
except ImportError:  # pragma: no cover - production app should provide this type.
    @dataclass(frozen=True)
    class LocalCoordinate:  # type: ignore[no-redef]
        north_m: float
        east_m: float
        down_m: float
        yaw_deg: float | None = None

from .enums import IndoorFrame
from .models import DockingTarget, LocalPose
from .slam import SimulatedSLAMProvider, SLAMProvider

logger = logging.getLogger(__name__)


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


def _accepts_keyword(fn: object, keyword: str) -> bool | None:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == keyword and parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            return True
    return False


@dataclass
class DroneLocalNavigationAdapter:
    drone: object
    slam_provider: SLAMProvider
    max_transform_concurrency: int = 16
    _last_speed_mps: float | None = field(default=None, init=False, repr=False)
    _speed_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def arm_and_takeoff_local(self, hover_alt_m: float) -> None:
        arm_and_takeoff = getattr(self.drone, "arm_and_takeoff", None)
        if not callable(arm_and_takeoff):
            raise RuntimeError("Drone does not expose arm_and_takeoff()")
        await asyncio.to_thread(arm_and_takeoff, float(hover_alt_m))

    async def goto_local_pose(
        self,
        pose: LocalPose,
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        await self.follow_local_path([pose], speed_mps=speed_mps, timeout_s=timeout_s)

    async def _set_speed_if_needed(self, speed_mps: float | None) -> None:
        if speed_mps is None:
            return
        speed = max(0.01, float(speed_mps))
        async with self._speed_lock:
            if self._last_speed_mps is not None and abs(float(self._last_speed_mps) - speed) < 1e-6:
                return
            attempted = False
            last_error: Exception | None = None
            for name in ("set_groundspeed", "set_speed", "set_cruise_speed"):
                setter = getattr(self.drone, name, None)
                if not callable(setter):
                    continue
                attempted = True
                try:
                    await asyncio.to_thread(setter, speed)
                    self._last_speed_mps = speed
                    return
                except Exception as exc:
                    last_error = exc
                    logger.warning("Drone speed setter %s failed", name, exc_info=True)
            if attempted:
                raise RuntimeError("Drone exposes speed setters, but all failed") from last_error
            logger.debug("Drone exposes no speed setter; continuing with autopilot default speed")

    async def _to_local_coordinate(self, pose: LocalPose) -> LocalCoordinate:
        resolved = await self.slam_provider.to_control_frame(
            pose,
            frame_id=IndoorFrame.ODOM.value,
        )
        return LocalCoordinate(
            north_m=float(resolved.y_m),
            east_m=float(resolved.x_m),
            down_m=-float(resolved.z_m),
            yaw_deg=resolved.yaw_deg,
        )

    async def _to_local_coordinates_bounded(self, path: Sequence[LocalPose]) -> list[LocalCoordinate]:
        concurrency = max(1, int(self.max_transform_concurrency))
        result: list[LocalCoordinate] = []
        for index in range(0, len(path), concurrency):
            batch = path[index : index + concurrency]
            result.extend(await asyncio.gather(*(self._to_local_coordinate(pose) for pose in batch)))
        return result

    async def follow_local_path(
        self,
        path: Sequence[LocalPose],
        *,
        speed_mps: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        poses = list(path)
        if not poses:
            return
        await self._set_speed_if_needed(speed_mps)
        control_path = await self._to_local_coordinates_bounded(poses)

        follow_fn = getattr(self.drone, "follow_local_setpoints", None)
        if not callable(follow_fn):
            raise RuntimeError("Drone does not expose follow_local_setpoints for indoor navigation")

        def _call_follow() -> None:
            if timeout_s is not None:
                supports_timeout = _accepts_keyword(follow_fn, "timeout_s")
                if supports_timeout is True:
                    follow_fn(control_path, timeout_s=float(timeout_s))
                    return
                if supports_timeout is None:
                    try:
                        follow_fn(control_path, timeout_s=float(timeout_s))
                        return
                    except TypeError:
                        logger.debug("follow_local_setpoints rejected timeout_s; retrying without it", exc_info=True)
            follow_fn(control_path)

        follow_task = asyncio.to_thread(_call_follow)
        if timeout_s is None:
            await follow_task
        else:
            # This cancels the awaiter. Python cannot forcibly stop a blocking
            # third-party drone call already running in a worker thread, so the
            # driver should still implement its own timeout when possible.
            await asyncio.wait_for(follow_task, timeout=max(0.01, float(timeout_s)))

    async def hold_position(self, *, timeout_s: float = 1.0) -> None:
        sleep_s = max(0.0, float(timeout_s))
        hold_fn = getattr(self.drone, "hold_position", None)
        if callable(hold_fn):
            try:
                await asyncio.to_thread(hold_fn)
                await asyncio.sleep(sleep_s)
                return
            except Exception:
                logger.warning("Drone hold_position() failed; trying LOITER fallback", exc_info=True)
        set_mode = getattr(self.drone, "set_mode", None)
        if callable(set_mode):
            try:
                await asyncio.to_thread(set_mode, "LOITER")
            except Exception:
                logger.warning("Drone LOITER fallback failed", exc_info=True)
        await asyncio.sleep(sleep_s)

    async def land_on_dock(self, target: DockingTarget | None = None) -> None:
        land_fn = getattr(self.drone, "land_on_dock", None)
        if callable(land_fn):
            try:
                supports_target = _accepts_keyword(land_fn, "target")
                if supports_target is True:
                    await asyncio.to_thread(land_fn, target=target)
                elif supports_target is False:
                    await asyncio.to_thread(land_fn)
                else:
                    try:
                        await asyncio.to_thread(land_fn, target)
                    except TypeError:
                        await asyncio.to_thread(land_fn)
                return
            except Exception:
                logger.warning("Precision land_on_dock() failed; falling back to safe_land()", exc_info=True)
        await self.safe_land()

    async def safe_land(self) -> None:
        land_fn = getattr(self.drone, "land", None)
        if not callable(land_fn):
            raise RuntimeError("Drone does not expose land() for safe landing")
        await asyncio.to_thread(land_fn)

    async def wait_until_disarmed(self, timeout_s: float = 900.0) -> None:
        wait_fn = getattr(self.drone, "wait_until_disarmed", None)
        if not callable(wait_fn):
            return
        timeout = max(0.01, float(timeout_s))

        def _call_wait() -> None:
            supports_timeout = _accepts_keyword(wait_fn, "timeout_s")
            if supports_timeout is True:
                wait_fn(timeout_s=timeout)
            else:
                wait_fn(timeout)

        await asyncio.wait_for(asyncio.to_thread(_call_wait), timeout=timeout)


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
        if not path:
            return
        resolved = [
            await self.slam_provider.to_control_frame(pose, frame_id=IndoorFrame.MAP.value)
            for pose in path
        ]
        self.slam_provider.move_along(resolved)

    async def hold_position(self, *, timeout_s: float = 1.0) -> None:
        await asyncio.sleep(max(0.0, float(timeout_s)))

    async def land_on_dock(self, target: DockingTarget | None = None) -> None:
        del target
        current = await self.slam_provider.get_pose()
        self.slam_provider.move_along([current.translated(dz_m=-float(current.z_m))])

    async def safe_land(self) -> None:
        await self.land_on_dock(None)

    async def wait_until_disarmed(self, timeout_s: float = 900.0) -> None:
        del timeout_s
