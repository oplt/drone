from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .enums import IndoorFrame
from .local_navigation import LocalNavigationAdapter
from .models import DockPose, DockingTarget, LocalPose


class DockingController(Protocol):
    async def initialize_dock_reference(self, dock: DockPose) -> bool: ...

    async def compute_dock_approach(self, current_pose: LocalPose, dock: DockPose) -> DockingTarget: ...

    async def run_precision_docking(self, current_pose: LocalPose, dock: DockPose) -> bool: ...

    async def confirm_docked(self, dock: DockPose) -> bool: ...


@dataclass
class PrecisionDockingController:
    navigator: LocalNavigationAdapter
    dock_search_radius_m: float = 1.5
    approach_speed_mps: float = 0.3
    descent_speed_mps: float = 0.15
    tolerance_m: float = 0.12
    _dock: DockPose | None = None

    async def initialize_dock_reference(self, dock: DockPose) -> bool:
        self._dock = dock
        return True

    async def compute_dock_approach(self, current_pose: LocalPose, dock: DockPose) -> DockingTarget:
        del current_pose
        return DockingTarget(
            target_pose=LocalPose(
                x_m=0.0,
                y_m=0.0,
                z_m=0.0,
                yaw_deg=dock.pose.yaw_deg,
                frame_id=IndoorFrame.DOCK.value,
            ),
            approach_pose=dock.entry_pose,
            marker_id=dock.marker_id,
            tolerance_m=float(self.tolerance_m),
            approach_speed_mps=float(self.approach_speed_mps),
            descent_speed_mps=float(self.descent_speed_mps),
            reference_frame=IndoorFrame.DOCK.value,
        )

    async def run_precision_docking(self, current_pose: LocalPose, dock: DockPose) -> bool:
        target = await self.compute_dock_approach(current_pose, dock)
        if target.approach_pose is not None:
            await self.navigator.goto_local_pose(
                target.approach_pose,
                speed_mps=float(target.approach_speed_mps),
            )
        await self.navigator.goto_local_pose(
            target.target_pose.translated(dz_m=0.25, frame_id=IndoorFrame.DOCK.value),
            speed_mps=float(target.approach_speed_mps),
        )
        await self.navigator.goto_local_pose(
            target.target_pose,
            speed_mps=float(target.descent_speed_mps),
        )
        await self.navigator.land_on_dock(target)
        return True

    async def confirm_docked(self, dock: DockPose) -> bool:
        del dock
        return True
