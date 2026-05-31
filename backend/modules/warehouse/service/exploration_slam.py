from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.infrastructure.warehouse.perception import build_warehouse_perception_port
from backend.modules.warehouse.planning.indoor.enums import IndoorFrame, OccupancyState
from backend.modules.warehouse.planning.indoor.models import (
    Frontier,
    LocalPose,
    MapSnapshot,
    OccupancyGrid,
    SLAMHealth,
)
from backend.modules.warehouse.planning.indoor.slam import SLAMProvider


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pose(payload: dict[str, object] | None) -> LocalPose:
    data = payload if isinstance(payload, dict) else {}
    return LocalPose(
        x_m=_float(data.get("x_m"), 0.0),
        y_m=_float(data.get("y_m"), 0.0),
        z_m=_float(data.get("z_m"), 0.0),
        yaw_deg=_float(data.get("yaw_deg"), 0.0) if data.get("yaw_deg") is not None else None,
        frame_id=str(data.get("frame_id") or IndoorFrame.MAP.value),
    )


def _grid(payload: dict[str, object]) -> OccupancyGrid:
    grid = OccupancyGrid(
        resolution_m=_float(payload.get("resolution_m"), 0.5),
        width=_int(payload.get("width"), 40),
        height=_int(payload.get("height"), 40),
        origin_x_m=_float(payload.get("origin_x_m"), -10.0),
        origin_y_m=_float(payload.get("origin_y_m"), -10.0),
        default_state=OccupancyState.UNKNOWN,
    )
    cells = payload.get("cells")
    if isinstance(cells, list):
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            state_raw = str(cell.get("state") or OccupancyState.UNKNOWN.value)
            try:
                state = OccupancyState(state_raw)
            except ValueError:
                state = OccupancyState.UNKNOWN
            grid.set_cell(_int(cell.get("x_idx"), -1), _int(cell.get("y_idx"), -1), state)
    return grid


@dataclass
class WarehousePerceptionSLAMProvider(SLAMProvider):
    """SLAMProvider backed by the Jetson ROS bridge nvblox exploration snapshot."""

    snapshot_cache_ttl_s: float = 0.2
    _cached_snapshot: object | None = field(default=None, init=False, repr=False)
    _cached_snapshot_at: float = field(default=0.0, init=False, repr=False)

    async def _snapshot(self):
        now = time.monotonic()
        if self._cached_snapshot is None or (now - self._cached_snapshot_at) > self.snapshot_cache_ttl_s:
            self._cached_snapshot = await build_warehouse_perception_port().exploration_snapshot()
            self._cached_snapshot_at = now
        return self._cached_snapshot

    async def get_pose(self) -> LocalPose:
        snapshot = await self._snapshot()
        return _pose(snapshot.pose)

    async def get_map_snapshot(self) -> MapSnapshot:
        snapshot = await self._snapshot()
        grid = _grid(snapshot.occupancy_grid)
        free_cells, occupied_cells, _unknown_cells = grid.counts()
        return MapSnapshot(
            occupancy_grid=grid,
            timestamp_s=time.time(),
            explored_cells=int(free_cells + occupied_cells),
            occupied_cells=int(occupied_cells),
            free_cells=int(free_cells),
            metadata=dict(snapshot.metadata),
        )

    async def get_localization_health(self) -> SLAMHealth:
        snapshot = await self._snapshot()
        health = snapshot.health if isinstance(snapshot.health, dict) else {}
        return SLAMHealth(
            tracking_ok=bool(health.get("tracking_ok", health.get("vslam_tracking", False))),
            map_ready=bool(health.get("map_ready", health.get("nvblox_ready", False))),
            lidar_streaming=bool(health.get("depth_healthy", True)),
            localization_confidence=_float(health.get("localization_confidence"), 0.0),
            drift_estimate_m=_float(health.get("odometry_drift_m"), 0.0),
            loop_closure_quality=_float(health.get("loop_closure_quality"), 0.0),
        )

    async def relocalize(self, timeout_s: float) -> bool:
        del timeout_s
        return bool((await self.get_localization_health()).tracking_ok)

    async def optimize_map(self) -> bool:
        return bool((await self.get_localization_health()).map_ready)

    async def to_control_frame(
        self, pose: LocalPose, *, frame_id: str = IndoorFrame.ODOM.value
    ) -> LocalPose:
        return LocalPose(
            x_m=pose.x_m,
            y_m=pose.y_m,
            z_m=pose.z_m,
            yaw_deg=pose.yaw_deg,
            frame_id=frame_id,
        )

    async def get_frontiers(self) -> list[Frontier] | None:
        return None
