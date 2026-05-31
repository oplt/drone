from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .enums import IndoorFrame
from .local_navigation import LocalNavigationAdapter
from .models import DockingTarget, DockPose, LocalPose


class DockingController(Protocol):
    async def initialize_dock_reference(self, dock: DockPose) -> bool: ...

    async def compute_dock_approach(
        self, current_pose: LocalPose, dock: DockPose
    ) -> DockingTarget: ...

    async def run_precision_docking(self, current_pose: LocalPose, dock: DockPose) -> bool: ...

    async def confirm_docked(self, dock: DockPose) -> bool: ...


@dataclass
class PrecisionDockingController:
    navigator: LocalNavigationAdapter
    dock_search_radius_m: float = 1.5
    approach_speed_mps: float = 0.3
    descent_speed_mps: float = 0.15
    tolerance_m: float = 0.12
    final_hover_offset_m: float = 0.25
    _dock: DockPose | None = None

    async def initialize_dock_reference(self, dock: DockPose) -> bool:
        self._dock = dock
        return bool(dock.dock_id and dock.pose is not None and dock.entry_pose is not None)

    async def compute_dock_approach(self, current_pose: LocalPose, dock: DockPose) -> DockingTarget:
        del current_pose
        dock_yaw = dock.pose.yaw_deg
        approach_pose = dock.entry_pose
        if approach_pose.yaw_deg is None and dock_yaw is not None:
            approach_pose = LocalPose(
                x_m=approach_pose.x_m,
                y_m=approach_pose.y_m,
                z_m=approach_pose.z_m,
                yaw_deg=dock_yaw,
                frame_id=approach_pose.frame_id,
            )
        return DockingTarget(
            target_pose=LocalPose(
                x_m=0.0,
                y_m=0.0,
                z_m=0.0,
                yaw_deg=dock_yaw,
                frame_id=IndoorFrame.DOCK.value,
            ),
            approach_pose=approach_pose,
            marker_id=dock.marker_id,
            tolerance_m=max(0.01, float(self.tolerance_m)),
            approach_speed_mps=max(0.01, float(self.approach_speed_mps)),
            descent_speed_mps=max(0.01, float(self.descent_speed_mps)),
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
            target.target_pose.translated(
                dz_m=max(0.0, float(self.final_hover_offset_m)),
                frame_id=IndoorFrame.DOCK.value,
            ),
            speed_mps=float(target.approach_speed_mps),
        )
        await self.navigator.goto_local_pose(
            target.target_pose,
            speed_mps=float(target.descent_speed_mps),
        )
        await self.navigator.land_on_dock(target)
        return await self.confirm_docked(dock)

    async def confirm_docked(self, dock: DockPose) -> bool:
        slam_provider = getattr(self.navigator, "slam_provider", None)
        if slam_provider is None:
            return True
        try:
            current = await slam_provider.get_pose()
            target = await slam_provider.to_control_frame(dock.pose, frame_id=current.frame_id)
        except Exception:
            return True
        return current.distance_to(target) <= max(float(self.tolerance_m), float(self.dock_search_radius_m))
