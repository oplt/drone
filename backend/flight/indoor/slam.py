from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Protocol, Sequence

from .enums import IndoorFrame, OccupancyState
from .models import DockPose, Frontier, LocalPose, MapSnapshot, OccupancyGrid, SLAMHealth


class SLAMProvider(Protocol):
    async def get_pose(self) -> LocalPose: ...

    async def get_map_snapshot(self) -> MapSnapshot: ...

    async def get_localization_health(self) -> SLAMHealth: ...

    async def relocalize(self, timeout_s: float) -> bool: ...

    async def optimize_map(self) -> bool: ...

    async def to_control_frame(self, pose: LocalPose, *, frame_id: str = IndoorFrame.ODOM.value) -> LocalPose: ...

    async def get_frontiers(self) -> list[Frontier] | None: ...


@dataclass
class SimulatedSLAMProvider:
    world_grid: OccupancyGrid
    initial_pose: LocalPose
    dock: DockPose | None = None
    reveal_radius_m: float = 2.5
    health: SLAMHealth = field(
        default_factory=lambda: SLAMHealth(
            tracking_ok=True,
            map_ready=False,
            lidar_streaming=True,
            localization_confidence=0.92,
            drift_estimate_m=0.05,
            loop_closure_quality=0.0,
        )
    )
    observed_grid: OccupancyGrid = field(init=False)
    current_pose: LocalPose = field(init=False)

    def __post_init__(self) -> None:
        self.current_pose = self.initial_pose
        self.observed_grid = OccupancyGrid(
            resolution_m=float(self.world_grid.resolution_m),
            width=int(self.world_grid.width),
            height=int(self.world_grid.height),
            origin_x_m=float(self.world_grid.origin_x_m),
            origin_y_m=float(self.world_grid.origin_y_m),
            default_state=OccupancyState.UNKNOWN,
        )
        self.reveal_around(self.current_pose, radius_m=self.reveal_radius_m)

    async def get_pose(self) -> LocalPose:
        return self.current_pose

    async def get_map_snapshot(self) -> MapSnapshot:
        free_cells, occupied_cells, unknown_cells = self.observed_grid.counts()
        self.health = replace(
            self.health,
            map_ready=(free_cells + occupied_cells) > 0,
        )
        return MapSnapshot(
            occupancy_grid=self.observed_grid.clone(),
            timestamp_s=time.time(),
            explored_cells=int(free_cells + occupied_cells),
            occupied_cells=int(occupied_cells),
            free_cells=int(free_cells),
            metadata={"unknown_cells": int(unknown_cells)},
        )

    async def get_localization_health(self) -> SLAMHealth:
        return self.health

    async def relocalize(self, timeout_s: float) -> bool:
        if not self.health.lidar_streaming:
            return False
        self.health = replace(
            self.health,
            tracking_ok=True,
            localization_confidence=max(0.9, float(self.health.localization_confidence)),
            drift_estimate_m=min(float(self.health.drift_estimate_m), 0.2),
        )
        return True

    async def optimize_map(self) -> bool:
        self.health = replace(
            self.health,
            drift_estimate_m=max(0.02, float(self.health.drift_estimate_m) * 0.5),
            loop_closure_quality=max(0.7, float(self.health.loop_closure_quality)),
            localization_confidence=max(0.85, float(self.health.localization_confidence)),
            last_loop_closure_s=time.time(),
        )
        return True

    async def to_control_frame(
        self,
        pose: LocalPose,
        *,
        frame_id: str = IndoorFrame.ODOM.value,
    ) -> LocalPose:
        if pose.frame_id == IndoorFrame.DOCK.value and self.dock is not None:
            resolved = LocalPose(
                x_m=float(self.dock.pose.x_m) + float(pose.x_m),
                y_m=float(self.dock.pose.y_m) + float(pose.y_m),
                z_m=float(self.dock.pose.z_m) + float(pose.z_m),
                yaw_deg=pose.yaw_deg if pose.yaw_deg is not None else self.dock.pose.yaw_deg,
                frame_id=IndoorFrame.MAP.value,
            )
        else:
            resolved = pose
        return replace(resolved, frame_id=frame_id)

    async def get_frontiers(self) -> list[Frontier] | None:
        return None

    def reveal_around(self, pose: LocalPose, *, radius_m: float) -> None:
        self.observed_grid.copy_visible_from(
            self.world_grid,
            center_pose=pose,
            radius_m=float(radius_m),
        )
        self.health = replace(
            self.health,
            map_ready=True,
            localization_confidence=max(0.6, float(self.health.localization_confidence)),
        )

    def move_along(self, poses: Sequence[LocalPose]) -> None:
        if not poses:
            return
        for pose in poses:
            self.current_pose = pose
            self.reveal_around(pose, radius_m=self.reveal_radius_m)

    def set_localization(self, *, confidence: float, tracking_ok: bool | None = None) -> None:
        self.health = replace(
            self.health,
            localization_confidence=float(confidence),
            tracking_ok=self.health.tracking_ok if tracking_ok is None else bool(tracking_ok),
        )
