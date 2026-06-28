from __future__ import annotations

import heapq
import math
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache

from .enums import IndoorFrame, LocalizationConfidence, OccupancyState

_SQRT2 = math.sqrt(2.0)
_NEIGHBOR8: tuple[tuple[int, int], ...] = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


def _coerce_occupancy_state(value: OccupancyState | str) -> OccupancyState:
    if isinstance(value, OccupancyState):
        return value
    return OccupancyState(str(value))


@lru_cache(maxsize=128)
def _inflation_offsets(inflate_cells: int) -> tuple[tuple[int, int], ...]:
    """Return cached square-footprint offsets for obstacle inflation.

    The previous implementation used a square inflation window. Keeping the same
    footprint preserves conservative clearance behavior while avoiding repeated
    nested-range allocation in A* and nearest-free searches.
    """
    radius = max(0, int(inflate_cells))
    if radius <= 0:
        return ()
    return tuple(
        (dx, dy)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
    )


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
    origin_z_m: float = 0.0
    origin_qx: float = 0.0
    origin_qy: float = 0.0
    origin_qz: float = 0.0
    origin_qw: float = 1.0
    default_state: OccupancyState | str = OccupancyState.UNKNOWN
    cells: dict[tuple[int, int], OccupancyState | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.resolution_m = max(float(self.resolution_m), 1e-6)
        self.width = max(0, int(self.width))
        self.height = max(0, int(self.height))
        self.origin_x_m = float(self.origin_x_m)
        self.origin_y_m = float(self.origin_y_m)
        self.origin_z_m = float(self.origin_z_m)
        self.origin_qx = float(self.origin_qx)
        self.origin_qy = float(self.origin_qy)
        self.origin_qz = float(self.origin_qz)
        self.origin_qw = float(self.origin_qw)
        if abs(self.origin_qw) < 1e-9 and abs(self.origin_qx) < 1e-9 and abs(self.origin_qy) < 1e-9 and abs(self.origin_qz) < 1e-9:
            self.origin_qw = 1.0
        self.default_state = _coerce_occupancy_state(self.default_state)

        # Normalize user-provided cells once. This prevents invalid strings or
        # out-of-bounds coordinates from corrupting counts(), to_dict(), and path
        # planning decisions later.
        normalized: dict[tuple[int, int], OccupancyState] = {}
        for raw_key, raw_state in self.cells.items():
            x_idx, y_idx = raw_key
            x = int(x_idx)
            y = int(y_idx)
            if not self.in_bounds(x, y):
                continue
            state = _coerce_occupancy_state(raw_state)
            if state != self.default_state:
                normalized[(x, y)] = state
        self.cells = normalized

    def clone(self) -> OccupancyGrid:
        return OccupancyGrid(
            resolution_m=float(self.resolution_m),
            width=int(self.width),
            height=int(self.height),
            origin_x_m=float(self.origin_x_m),
            origin_y_m=float(self.origin_y_m),
            origin_z_m=float(self.origin_z_m),
            origin_qx=float(self.origin_qx),
            origin_qy=float(self.origin_qy),
            origin_qz=float(self.origin_qz),
            origin_qw=float(self.origin_qw),
            default_state=self.default_state,
            cells=dict(self.cells),
        )

    def origin_yaw_rad(self) -> float:
        qx = float(self.origin_qx)
        qy = float(self.origin_qy)
        qz = float(self.origin_qz)
        qw = float(self.origin_qw)
        siny_cosp = 2.0 * (qw * qz + qx * qy)
        cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
        return math.atan2(siny_cosp, cosy_cosp)

    @staticmethod
    def _rotate_xy(x: float, y: float, yaw_rad: float) -> tuple[float, float]:
        c = math.cos(yaw_rad)
        s = math.sin(yaw_rad)
        return x * c - y * s, x * s + y * c

    def in_bounds(self, x_idx: int, y_idx: int) -> bool:
        return 0 <= int(x_idx) < int(self.width) and 0 <= int(y_idx) < int(self.height)

    def set_cell(self, x_idx: int, y_idx: int, state: OccupancyState | str) -> None:
        x = int(x_idx)
        y = int(y_idx)
        if not self.in_bounds(x, y):
            return
        normalized_state = _coerce_occupancy_state(state)
        key = (x, y)
        if normalized_state == self.default_state:
            self.cells.pop(key, None)
            return
        self.cells[key] = normalized_state

    def set_cells(
        self,
        coords: Iterable[tuple[int, int]],
        state: OccupancyState | str,
    ) -> None:
        normalized_state = _coerce_occupancy_state(state)
        for x_idx, y_idx in coords:
            self.set_cell(x_idx, y_idx, normalized_state)

    def get_cell(self, x_idx: int, y_idx: int) -> OccupancyState:
        x = int(x_idx)
        y = int(y_idx)
        if x < 0 or x >= int(self.width) or y < 0 or y >= int(self.height):
            return OccupancyState.OCCUPIED
        return self.cells.get((x, y), self.default_state)  # type: ignore[return-value]

    def iter_cells(self) -> Iterator[OccupancyCell]:
        cells = self.cells
        default_state = self.default_state
        for y_idx in range(int(self.height)):
            for x_idx in range(int(self.width)):
                yield OccupancyCell(
                    x_idx=x_idx,
                    y_idx=y_idx,
                    state=cells.get((x_idx, y_idx), default_state),  # type: ignore[arg-type]
                )

    def world_to_cell(self, pose: LocalPose) -> tuple[int, int]:
        resolution = float(self.resolution_m)
        dx = float(pose.x_m) - float(self.origin_x_m)
        dy = float(pose.y_m) - float(self.origin_y_m)
        local_x, local_y = self._rotate_xy(dx, dy, -self.origin_yaw_rad())
        x_idx = int(math.floor(local_x / resolution))
        y_idx = int(math.floor(local_y / resolution))
        return x_idx, y_idx

    def cell_to_pose(
        self,
        x_idx: int,
        y_idx: int,
        *,
        z_m: float = 0.0,
        frame_id: str = IndoorFrame.MAP.value,
    ) -> LocalPose:
        resolution = float(self.resolution_m)
        local_x = (float(x_idx) + 0.5) * resolution
        local_y = (float(y_idx) + 0.5) * resolution
        world_x, world_y = self._rotate_xy(local_x, local_y, self.origin_yaw_rad())
        return LocalPose(
            x_m=float(self.origin_x_m) + world_x,
            y_m=float(self.origin_y_m) + world_y,
            z_m=float(self.origin_z_m) + float(z_m),
            frame_id=frame_id,
        )

    def neighbors8(self, x_idx: int, y_idx: int) -> Iterator[tuple[int, int]]:
        width = int(self.width)
        height = int(self.height)
        x = int(x_idx)
        y = int(y_idx)
        for dx, dy in _NEIGHBOR8:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < width and 0 <= ny < height:
                yield nx, ny

    def adjacent_unknown(self, x_idx: int, y_idx: int) -> bool:
        cells = self.cells
        default_state = self.default_state
        width = int(self.width)
        height = int(self.height)
        x = int(x_idx)
        y = int(y_idx)
        for dx, dy in _NEIGHBOR8:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < width and 0 <= ny < height and cells.get((nx, ny), default_state) == OccupancyState.UNKNOWN:
                return True
        return False

    def clearance_at(self, pose: LocalPose, *, search_radius_m: float = 3.0) -> float:
        origin = self.world_to_cell(pose)
        radius_m = max(0.0, float(search_radius_m))
        resolution = float(self.resolution_m)
        max_cells = int(math.ceil(radius_m / resolution))
        max_cells_sq = max_cells * max_cells
        best_cells_sq = max_cells_sq

        if max_cells == 0:
            return 0.0 if self.get_cell(origin[0], origin[1]) == OccupancyState.OCCUPIED else radius_m

        # Sparse fast path for the usual SLAM map shape: unknown default, explicit
        # free/occupied observations. Scanning only explicit occupied cells avoids
        # O(radius²) work when the obstacle set is sparse.
        if self.default_state != OccupancyState.OCCUPIED and self.cells:
            min_x = origin[0] - max_cells
            max_x = origin[0] + max_cells
            min_y = origin[1] - max_cells
            max_y = origin[1] + max_cells
            for (x_idx, y_idx), state in self.cells.items():
                if state != OccupancyState.OCCUPIED:
                    continue
                if x_idx < min_x or x_idx > max_x or y_idx < min_y or y_idx > max_y:
                    continue
                dx = x_idx - origin[0]
                dy = y_idx - origin[1]
                dist_sq = dx * dx + dy * dy
                if dist_sq <= max_cells_sq and dist_sq < best_cells_sq:
                    best_cells_sq = dist_sq
                    if best_cells_sq == 0:
                        return 0.0
            return min(radius_m, math.sqrt(float(best_cells_sq)) * resolution)

        for dy in range(-max_cells, max_cells + 1):
            dy_sq = dy * dy
            for dx in range(-max_cells, max_cells + 1):
                dist_sq = dx * dx + dy_sq
                if dist_sq > max_cells_sq:
                    continue
                x_idx = origin[0] + dx
                y_idx = origin[1] + dy
                if self.get_cell(x_idx, y_idx) != OccupancyState.OCCUPIED:
                    continue
                if dist_sq < best_cells_sq:
                    best_cells_sq = dist_sq
                    if best_cells_sq == 0:
                        return 0.0
        return min(radius_m, math.sqrt(float(best_cells_sq)) * resolution)

    def _is_traversable_cached(
        self,
        x_idx: int,
        y_idx: int,
        *,
        inflate_cells: int,
        cache: dict[tuple[int, int], bool] | None = None,
    ) -> bool:
        key = (int(x_idx), int(y_idx))
        if cache is not None and key in cache:
            return cache[key]
        result = self._is_traversable_no_cache(key[0], key[1], inflate_cells=inflate_cells)
        if cache is not None:
            cache[key] = result
        return result

    def _is_traversable_no_cache(self, x_idx: int, y_idx: int, *, inflate_cells: int) -> bool:
        if self.get_cell(x_idx, y_idx) != OccupancyState.FREE:
            return False
        for dx, dy in _inflation_offsets(int(inflate_cells)):
            if self.get_cell(int(x_idx) + dx, int(y_idx) + dy) == OccupancyState.OCCUPIED:
                return False
        return True

    def is_traversable(self, x_idx: int, y_idx: int, *, clearance_m: float = 0.0) -> bool:
        inflate_cells = int(math.ceil(max(0.0, float(clearance_m)) / float(self.resolution_m)))
        return self._is_traversable_no_cache(int(x_idx), int(y_idx), inflate_cells=inflate_cells)

    def nearest_free_cell(
        self,
        pose: LocalPose,
        *,
        clearance_m: float = 0.0,
        max_radius_m: float = 5.0,
    ) -> tuple[int, int] | None:
        start = self.world_to_cell(pose)
        max_radius_cells = int(math.ceil(max(0.0, float(max_radius_m)) / float(self.resolution_m)))
        max_radius_sq = max_radius_cells * max_radius_cells
        inflate_cells = int(math.ceil(max(0.0, float(clearance_m)) / float(self.resolution_m)))
        traversable_cache: dict[tuple[int, int], bool] = {}
        visited: set[tuple[int, int]] = {start}
        heap: list[tuple[int, int, int, int]] = [(0, 0, start[0], start[1])]

        while heap:
            dist_sq, manhattan, x_idx, y_idx = heapq.heappop(heap)
            del manhattan
            if dist_sq > max_radius_sq:
                continue
            if not self.in_bounds(x_idx, y_idx):
                continue
            if self._is_traversable_cached(
                x_idx,
                y_idx,
                inflate_cells=inflate_cells,
                cache=traversable_cache,
            ):
                return (x_idx, y_idx)
            for nx, ny in self.neighbors8(x_idx, y_idx):
                key = (nx, ny)
                if key in visited:
                    continue
                dx = nx - start[0]
                dy = ny - start[1]
                neighbor_dist_sq = dx * dx + dy * dy
                if neighbor_dist_sq > max_radius_sq:
                    continue
                visited.add(key)
                heapq.heappush(heap, (neighbor_dist_sq, abs(dx) + abs(dy), nx, ny))
        return None

    def astar_path(
        self,
        start_pose: LocalPose,
        end_pose: LocalPose,
        *,
        clearance_m: float = 0.0,
    ) -> list[LocalPose]:
        clearance = max(0.0, float(clearance_m))
        start = self.nearest_free_cell(start_pose, clearance_m=clearance)
        goal = self.nearest_free_cell(end_pose, clearance_m=clearance)
        if start is None or goal is None:
            return []

        if start == goal:
            return [self.cell_to_pose(*start, z_m=start_pose.z_m)]

        inflate_cells = int(math.ceil(clearance / float(self.resolution_m)))
        traversable_cache: dict[tuple[int, int], bool] = {}

        def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
            return math.hypot(float(a[0] - b[0]), float(a[1] - b[1]))

        open_heap: list[tuple[float, float, tuple[int, int]]] = [(heuristic(start, goal), 0.0, start)]
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], float] = {start: 0.0}
        closed: set[tuple[int, int]] = set()

        while open_heap:
            _priority, current_g, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            if current_g > g_score.get(current, float("inf")):
                continue
            if current == goal:
                cells: list[tuple[int, int]] = [current]
                while current in came_from:
                    current = came_from[current]
                    cells.append(current)
                cells.reverse()
                result: list[LocalPose] = []
                last_idx = len(cells) - 1
                for idx, cell in enumerate(cells):
                    z_m = float(start_pose.z_m) if idx < last_idx else float(end_pose.z_m)
                    result.append(self.cell_to_pose(cell[0], cell[1], z_m=z_m))
                return result

            closed.add(current)
            for neighbor in self.neighbors8(*current):
                if neighbor in closed:
                    continue
                if not self._is_traversable_cached(
                    neighbor[0],
                    neighbor[1],
                    inflate_cells=inflate_cells,
                    cache=traversable_cache,
                ):
                    continue

                is_diagonal = neighbor[0] != current[0] and neighbor[1] != current[1]
                if is_diagonal:
                    # Prevent unsafe corner cutting through two blocked cardinal
                    # cells. This is a correctness issue for inflated occupancy
                    # grids and indoor drones operating near racks/walls.
                    side_a = (neighbor[0], current[1])
                    side_b = (current[0], neighbor[1])
                    if not self._is_traversable_cached(
                        side_a[0], side_a[1], inflate_cells=inflate_cells, cache=traversable_cache
                    ) or not self._is_traversable_cached(
                        side_b[0], side_b[1], inflate_cells=inflate_cells, cache=traversable_cache
                    ):
                        continue

                step_cost = _SQRT2 if is_diagonal else 1.0
                tentative = g_score[current] + step_cost
                if tentative >= g_score.get(neighbor, float("inf")):
                    continue
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                heapq.heappush(open_heap, (tentative + heuristic(neighbor, goal), tentative, neighbor))

        return []

    def frontier_groups(self) -> list[list[tuple[int, int]]]:
        groups: list[list[tuple[int, int]]] = []
        visited: set[tuple[int, int]] = set()
        cells = self.cells
        default_state = self.default_state
        width = int(self.width)
        height = int(self.height)

        def is_frontier_cell(x_idx: int, y_idx: int) -> bool:
            if cells.get((x_idx, y_idx), default_state) != OccupancyState.FREE:
                return False
            for dx, dy in _NEIGHBOR8:
                nx = x_idx + dx
                ny = y_idx + dy
                if 0 <= nx < width and 0 <= ny < height and cells.get((nx, ny), default_state) == OccupancyState.UNKNOWN:
                    return True
            return False

        if default_state == OccupancyState.FREE:
            candidates: Iterable[tuple[int, int]] = (
                (x_idx, y_idx) for y_idx in range(height) for x_idx in range(width)
            )
        else:
            candidates = (
                (x_idx, y_idx)
                for (x_idx, y_idx), state in cells.items()
                if state == OccupancyState.FREE and 0 <= x_idx < width and 0 <= y_idx < height
            )

        for key in candidates:
            if key in visited or not is_frontier_cell(*key):
                continue
            group: list[tuple[int, int]] = []
            queue: deque[tuple[int, int]] = deque([key])
            visited.add(key)
            while queue:
                current = queue.popleft()
                if not is_frontier_cell(*current):
                    continue
                group.append(current)
                for neighbor in self.neighbors8(*current):
                    if neighbor in visited or not is_frontier_cell(*neighbor):
                        continue
                    visited.add(neighbor)
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
        radius_cells = int(math.ceil(max(0.0, float(radius_m)) / float(self.resolution_m)))
        radius_cells_sq = radius_cells * radius_cells
        center = self.world_to_cell(center_pose)
        min_x = max(0, center[0] - radius_cells)
        max_x = min(int(self.width) - 1, center[0] + radius_cells)
        min_y = max(0, center[1] - radius_cells)
        max_y = min(int(self.height) - 1, center[1] + radius_cells)
        other_cells = other.cells
        other_default = other.default_state
        default_state = self.default_state
        same_geometry = (
            math.isclose(float(self.resolution_m), float(other.resolution_m))
            and math.isclose(float(self.origin_x_m), float(other.origin_x_m))
            and math.isclose(float(self.origin_y_m), float(other.origin_y_m))
            and math.isclose(float(self.origin_z_m), float(other.origin_z_m))
            and math.isclose(float(self.origin_qx), float(other.origin_qx))
            and math.isclose(float(self.origin_qy), float(other.origin_qy))
            and math.isclose(float(self.origin_qz), float(other.origin_qz))
            and math.isclose(float(self.origin_qw), float(other.origin_qw))
        )

        for y_idx in range(min_y, max_y + 1):
            dy = y_idx - center[1]
            dy_sq = dy * dy
            for x_idx in range(min_x, max_x + 1):
                dx = x_idx - center[0]
                if dx * dx + dy_sq > radius_cells_sq:
                    continue
                key = (x_idx, y_idx)
                if same_geometry:
                    state = other_cells.get(key, other_default)
                else:
                    pose = self.cell_to_pose(x_idx, y_idx)
                    state = other.get_cell(*other.world_to_cell(pose))
                if state == default_state:
                    self.cells.pop(key, None)
                else:
                    self.cells[key] = state

    def counts(self) -> tuple[int, int, int]:
        total = max(0, int(self.width) * int(self.height))
        explicit_free = 0
        explicit_occupied = 0
        explicit_unknown = 0
        for state in self.cells.values():
            if state == OccupancyState.FREE:
                explicit_free += 1
            elif state == OccupancyState.OCCUPIED:
                explicit_occupied += 1
            else:
                explicit_unknown += 1
        default_count = max(0, total - len(self.cells))
        free = explicit_free + (default_count if self.default_state == OccupancyState.FREE else 0)
        occupied = explicit_occupied + (default_count if self.default_state == OccupancyState.OCCUPIED else 0)
        unknown = explicit_unknown + (default_count if self.default_state == OccupancyState.UNKNOWN else 0)
        return free, occupied, unknown

    @staticmethod
    def path_length_m(path: Iterable[LocalPose]) -> float:
        iterator = iter(path)
        try:
            previous = next(iterator)
        except StopIteration:
            return 0.0
        total = 0.0
        for current in iterator:
            total += previous.distance_to(current)
            previous = current
        return float(total)

    def to_dict(self) -> dict[str, object]:
        return {
            "resolution_m": float(self.resolution_m),
            "width": int(self.width),
            "height": int(self.height),
            "origin_x_m": float(self.origin_x_m),
            "origin_y_m": float(self.origin_y_m),
            "origin_z_m": float(self.origin_z_m),
            "origin_qx": float(self.origin_qx),
            "origin_qy": float(self.origin_qy),
            "origin_qz": float(self.origin_qz),
            "origin_qw": float(self.origin_qw),
            "default_state": self.default_state.value,
            "cells": [
                {"x_idx": x_idx, "y_idx": y_idx, "state": state.value}
                for (x_idx, y_idx), state in sorted(self.cells.items())
            ],
        }
