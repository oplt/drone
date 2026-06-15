from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from .enums import IndoorFrame
from .local_navigation import LocalNavigationAdapter
from .models import DockingTarget, DockPose, LocalPose

logger = logging.getLogger(__name__)


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
        valid = bool(getattr(dock, "dock_id", None) and getattr(dock, "pose", None) is not None and getattr(dock, "entry_pose", None) is not None)
        self._dock = dock if valid else None
        return valid

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
            logger.warning("Cannot confirm docking: navigator has no SLAM provider")
            return False
        try:
            current = await slam_provider.get_pose()
            target = await slam_provider.to_control_frame(dock.pose, frame_id=current.frame_id)
        except Exception:
            logger.exception("Cannot confirm docking because pose lookup failed")
            return False

        # dock_search_radius_m is useful while searching for a dock marker. Final
        # confirmation must use precision tolerance, otherwise a drone can be more
        # than a metre from the pad and still be reported as docked.
        tolerance = max(0.01, float(self.tolerance_m))
        return current.distance_to(target) <= tolerance
