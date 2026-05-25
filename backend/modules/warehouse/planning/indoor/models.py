from __future__ import annotations

import heapq
import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .enums import IndoorFrame, LocalizationConfidence, OccupancyState


@dataclass(frozen=True)
class LocalPose:
    x_m: float
    y_m: float
    z_m: float = 0.0
    yaw_deg: float | None = None
    frame_id: str = IndoorFrame.MAP.value

    def distance_to(self, other: LocalPose) -> float:
        return math.sqrt(
            (float(other.x_m) - float(self.x_m)) ** 2
            + (float(other.y_m) - float(self.y_m)) ** 2
            + (float(other.z_m) - float(self.z_m)) ** 2
        )

    def planar_distance_to(self, other: LocalPose) -> float:
        return math.hypot(
            float(other.x_m) - float(self.x_m),
            float(other.y_m) - float(self.y_m),
        )

    def translated(
        self,
        *,
        dx_m: float = 0.0,
        dy_m: float = 0.0,
        dz_m: float = 0.0,
        frame_id: str | None = None,
    ) -> LocalPose:
        return LocalPose(
            x_m=float(self.x_m) + float(dx_m),
            y_m=float(self.y_m) + float(dy_m),
            z_m=float(self.z_m) + float(dz_m),
            yaw_deg=self.yaw_deg,
            frame_id=frame_id or self.frame_id,
        )


@dataclass(frozen=True)
class LocalWaypoint:
    pose: LocalPose
    speed_mps: float | None = None
    tolerance_m: float = 0.4
    purpose: str = "transit"


@dataclass(frozen=True)
class DockPose:
    dock_id: str
    pose: LocalPose
    entry_pose: LocalPose
    exit_pose: LocalPose
    marker_id: str | None = None
    precision_required: bool = True
    dock_frame_id: str = IndoorFrame.DOCK.value


@dataclass(frozen=True)
class OccupancyCell:
    x_idx: int
    y_idx: int
    state: OccupancyState


@dataclass(frozen=True)
class Frontier:
    frontier_id: str
    centroid: LocalPose
    approach_pose: LocalPose
    cell_count: int
    information_gain: float
    path_length_m: float
    clearance_m: float
    localization_confidence: float
    drift_penalty: float
    return_graph_distance_m: float
    battery_cost_pct: float
    corridor_preference: float
    score: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExplorationNode:
    node_id: str
    pose: LocalPose
    confidence: float
    confirmed: bool = True
    connected_to_dock: bool = False
    kind: str = "skeleton"


@dataclass(frozen=True)
class SLAMHealth:
    tracking_ok: bool
    map_ready: bool
    lidar_streaming: bool
    localization_confidence: float
    drift_estimate_m: float = 0.0
    loop_closure_quality: float = 0.0
    last_loop_closure_s: float | None = None

    @property
    def confidence_level(self) -> LocalizationConfidence:
        value = float(self.localization_confidence)
        if not self.tracking_ok or value <= 0.2:
            return LocalizationConfidence.LOST
        if value < 0.5:
            return LocalizationConfidence.LOW
        if value < 0.8:
            return LocalizationConfidence.MEDIUM
        return LocalizationConfidence.HIGH


@dataclass(frozen=True)
class ReturnMarginEstimate:
    can_continue: bool
    can_return: bool
    should_return_now: bool
    projected_remaining_pct: float
    required_reserve_pct: float
    outbound_cost_pct: float
    explore_cost_pct: float
    return_cost_pct: float
    total_cost_pct: float
    return_path_length_m: float
    reason: str


@dataclass(frozen=True)
class DockingTarget:
    target_pose: LocalPose
    approach_pose: LocalPose | None = None
    marker_id: str | None = None
    tolerance_m: float = 0.12
    approach_speed_mps: float = 0.3
    descent_speed_mps: float = 0.15
    reference_frame: str = IndoorFrame.DOCK.value


@dataclass(frozen=True)
class MapSnapshot:
    occupancy_grid: OccupancyGrid
    timestamp_s: float
    map_frame: str = IndoorFrame.MAP.value
    explored_cells: int = 0
    occupied_cells: int = 0
    free_cells: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp_s": float(self.timestamp_s),
            "map_frame": self.map_frame,
            "explored_cells": int(self.explored_cells),
            "occupied_cells": int(self.occupied_cells),
            "free_cells": int(self.free_cells),
            "metadata": dict(self.metadata),
            "occupancy_grid": self.occupancy_grid.to_dict(),
        }


@dataclass
class OccupancyGrid:
    resolution_m: float
    width: int
    height: int
    origin_x_m: float = 0.0
    origin_y_m: float = 0.0
    default_state: OccupancyState = OccupancyState.UNKNOWN
    cells: dict[tuple[int, int], OccupancyState] = field(default_factory=dict)

    def clone(self) -> OccupancyGrid:
        return OccupancyGrid(
            resolution_m=float(self.resolution_m),
            width=int(self.width),
            height=int(self.height),
            origin_x_m=float(self.origin_x_m),
            origin_y_m=float(self.origin_y_m),
            default_state=self.default_state,
            cells=dict(self.cells),
        )

    def in_bounds(self, x_idx: int, y_idx: int) -> bool:
        return 0 <= int(x_idx) < int(self.width) and 0 <= int(y_idx) < int(self.height)

    def set_cell(self, x_idx: int, y_idx: int, state: OccupancyState) -> None:
        key = (int(x_idx), int(y_idx))
        if not self.in_bounds(*key):
            return
        if state == self.default_state:
            self.cells.pop(key, None)
            return
        self.cells[key] = state

    def set_cells(
        self,
        coords: Iterable[tuple[int, int]],
        state: OccupancyState,
    ) -> None:
        for x_idx, y_idx in coords:
            self.set_cell(x_idx, y_idx, state)

    def get_cell(self, x_idx: int, y_idx: int) -> OccupancyState:
        key = (int(x_idx), int(y_idx))
        if not self.in_bounds(*key):
            return OccupancyState.OCCUPIED
        return self.cells.get(key, self.default_state)

    def iter_cells(self) -> Iterator[OccupancyCell]:
        for y_idx in range(self.height):
            for x_idx in range(self.width):
                yield OccupancyCell(
                    x_idx=x_idx,
                    y_idx=y_idx,
                    state=self.get_cell(x_idx, y_idx),
                )

    def world_to_cell(self, pose: LocalPose) -> tuple[int, int]:
        x_idx = int(
            math.floor((float(pose.x_m) - float(self.origin_x_m)) / float(self.resolution_m))
        )
        y_idx = int(
            math.floor((float(pose.y_m) - float(self.origin_y_m)) / float(self.resolution_m))
        )
        return x_idx, y_idx

    def cell_to_pose(
        self,
        x_idx: int,
        y_idx: int,
        *,
        z_m: float = 0.0,
        frame_id: str = IndoorFrame.MAP.value,
    ) -> LocalPose:
        return LocalPose(
            x_m=float(self.origin_x_m) + ((float(x_idx) + 0.5) * float(self.resolution_m)),
            y_m=float(self.origin_y_m) + ((float(y_idx) + 0.5) * float(self.resolution_m)),
            z_m=float(z_m),
            frame_id=frame_id,
        )

    def neighbors8(self, x_idx: int, y_idx: int) -> Iterator[tuple[int, int]]:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x_idx + dx, y_idx + dy
                if self.in_bounds(nx, ny):
                    yield nx, ny

    def adjacent_unknown(self, x_idx: int, y_idx: int) -> bool:
        for nx, ny in self.neighbors8(x_idx, y_idx):
            if self.get_cell(nx, ny) == OccupancyState.UNKNOWN:
                return True
        return False

    def clearance_at(self, pose: LocalPose, *, search_radius_m: float = 3.0) -> float:
        origin = self.world_to_cell(pose)
        max_cells = max(1, int(math.ceil(float(search_radius_m) / float(self.resolution_m))))
        best = float(search_radius_m)
        for dy in range(-max_cells, max_cells + 1):
            for dx in range(-max_cells, max_cells + 1):
                x_idx = origin[0] + dx
                y_idx = origin[1] + dy
                if self.get_cell(x_idx, y_idx) != OccupancyState.OCCUPIED:
                    continue
                dist_cells = math.hypot(dx, dy)
                best = min(best, dist_cells * float(self.resolution_m))
        return best

    def is_traversable(self, x_idx: int, y_idx: int, *, clearance_m: float = 0.0) -> bool:
        if self.get_cell(x_idx, y_idx) != OccupancyState.FREE:
            return False
        inflate_cells = int(math.ceil(float(clearance_m) / float(self.resolution_m)))
        for dy in range(-inflate_cells, inflate_cells + 1):
            for dx in range(-inflate_cells, inflate_cells + 1):
                nx, ny = x_idx + dx, y_idx + dy
                if self.get_cell(nx, ny) == OccupancyState.OCCUPIED:
                    return False
        return True

    def nearest_free_cell(
        self,
        pose: LocalPose,
        *,
        clearance_m: float = 0.0,
        max_radius_m: float = 5.0,
    ) -> tuple[int, int] | None:
        start = self.world_to_cell(pose)
        max_radius_cells = max(1, int(math.ceil(float(max_radius_m) / float(self.resolution_m))))
        visited: set[tuple[int, int]] = set()
        queue: list[tuple[int, int, int]] = [(0, start[0], start[1])]
        while queue:
            distance, x_idx, y_idx = queue.pop(0)
            key = (x_idx, y_idx)
            if key in visited or not self.in_bounds(x_idx, y_idx):
                continue
            visited.add(key)
            if self.is_traversable(x_idx, y_idx, clearance_m=clearance_m):
                return key
            if distance >= max_radius_cells:
                continue
            for nx, ny in self.neighbors8(x_idx, y_idx):
                queue.append((distance + 1, nx, ny))
        return None

    def astar_path(
        self,
        start_pose: LocalPose,
        end_pose: LocalPose,
        *,
        clearance_m: float = 0.0,
    ) -> list[LocalPose]:
        start = self.nearest_free_cell(start_pose, clearance_m=clearance_m)
        goal = self.nearest_free_cell(end_pose, clearance_m=clearance_m)
        if start is None or goal is None:
            return []

        if start == goal:
            return [self.cell_to_pose(*start, z_m=start_pose.z_m)]

        def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
            return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))

        open_heap: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], float] = {start: 0.0}

        while open_heap:
            _priority, current = heapq.heappop(open_heap)
            if current == goal:
                cells: list[tuple[int, int]] = [current]
                while current in came_from:
                    current = came_from[current]
                    cells.append(current)
                cells.reverse()
                result: list[LocalPose] = []
                for idx, cell in enumerate(cells):
                    z_m = float(start_pose.z_m) if idx < len(cells) - 1 else float(end_pose.z_m)
                    result.append(self.cell_to_pose(cell[0], cell[1], z_m=z_m))
                return result

            for neighbor in self.neighbors8(*current):
                if not self.is_traversable(*neighbor, clearance_m=clearance_m):
                    continue
                step_cost = (
                    math.sqrt(2.0)
                    if neighbor[0] != current[0] and neighbor[1] != current[1]
                    else 1.0
                )
                tentative = g_score[current] + step_cost
                if tentative >= g_score.get(neighbor, float("inf")):
                    continue
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                priority = tentative + heuristic(neighbor, goal)
                heapq.heappush(open_heap, (priority, neighbor))

        return []

    def frontier_groups(self) -> list[list[tuple[int, int]]]:
        groups: list[list[tuple[int, int]]] = []
        visited: set[tuple[int, int]] = set()
        for cell in self.iter_cells():
            key = (cell.x_idx, cell.y_idx)
            if key in visited:
                continue
            if cell.state != OccupancyState.FREE or not self.adjacent_unknown(*key):
                continue
            group: list[tuple[int, int]] = []
            queue = [key]
            while queue:
                current = queue.pop()
                if current in visited:
                    continue
                visited.add(current)
                if self.get_cell(*current) != OccupancyState.FREE or not self.adjacent_unknown(
                    *current
                ):
                    continue
                group.append(current)
                for neighbor in self.neighbors8(*current):
                    if neighbor not in visited:
                        queue.append(neighbor)
            if group:
                groups.append(group)
        return groups

    def copy_visible_from(
        self,
        other: OccupancyGrid,
        *,
        center_pose: LocalPose,
        radius_m: float,
    ) -> None:
        radius_cells = max(1, int(math.ceil(float(radius_m) / float(self.resolution_m))))
        center = self.world_to_cell(center_pose)
        for dy in range(-radius_cells, radius_cells + 1):
            for dx in range(-radius_cells, radius_cells + 1):
                x_idx, y_idx = center[0] + dx, center[1] + dy
                if not self.in_bounds(x_idx, y_idx):
                    continue
                if math.hypot(dx, dy) > radius_cells:
                    continue
                self.set_cell(x_idx, y_idx, other.get_cell(x_idx, y_idx))

    def counts(self) -> tuple[int, int, int]:
        free = 0
        occupied = 0
        unknown = 0
        for cell in self.iter_cells():
            if cell.state == OccupancyState.FREE:
                free += 1
            elif cell.state == OccupancyState.OCCUPIED:
                occupied += 1
            else:
                unknown += 1
        return free, occupied, unknown

    @staticmethod
    def path_length_m(path: Iterable[LocalPose]) -> float:
        points = list(path)
        if len(points) < 2:
            return 0.0
        return float(sum(a.distance_to(b) for a, b in zip(points, points[1:])))

    def to_dict(self) -> dict[str, object]:
        return {
            "resolution_m": float(self.resolution_m),
            "width": int(self.width),
            "height": int(self.height),
            "origin_x_m": float(self.origin_x_m),
            "origin_y_m": float(self.origin_y_m),
            "cells": [
                {"x_idx": x_idx, "y_idx": y_idx, "state": state.value}
                for (x_idx, y_idx), state in sorted(self.cells.items())
            ],
        }
