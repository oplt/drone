from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from .models import DockPose, ExplorationNode, LocalPose, MapSnapshot


@dataclass
class ExplorationGraph:
    nodes: dict[str, ExplorationNode] = field(default_factory=dict)
    edges: dict[str, dict[str, float]] = field(default_factory=dict)
    _node_counter: itertools.count = field(default_factory=lambda: itertools.count(1), repr=False)
    dock_node_id: str | None = None
    visit_order: list[str] = field(default_factory=list)

    def ensure_dock_node(self, dock: DockPose) -> ExplorationNode:
        if self.dock_node_id and self.dock_node_id in self.nodes:
            return self.nodes[self.dock_node_id]
        dock_node = self.add_node(
            dock.pose,
            confidence=1.0,
            connected_to_dock=True,
            kind="dock",
            node_id=f"dock_{dock.dock_id}",
        )
        self.dock_node_id = dock_node.node_id
        return dock_node

    def add_node(
        self,
        pose: LocalPose,
        *,
        confidence: float,
        connected_to_dock: bool,
        kind: str,
        node_id: str | None = None,
    ) -> ExplorationNode:
        resolved_id = node_id or f"node_{next(self._node_counter)}"
        node = ExplorationNode(
            node_id=resolved_id,
            pose=pose,
            confidence=float(confidence),
            confirmed=True,
            connected_to_dock=bool(connected_to_dock),
            kind=kind,
        )
        self.nodes[resolved_id] = node
        self.edges.setdefault(resolved_id, {})
        self.visit_order.append(resolved_id)
        return node

    def connect_nodes(self, node_a: str, node_b: str, cost_m: float) -> None:
        if node_a == node_b or node_a not in self.nodes or node_b not in self.nodes:
            return
        weight = float(max(0.0, cost_m))
        self.edges.setdefault(node_a, {})[node_b] = weight
        self.edges.setdefault(node_b, {})[node_a] = weight

    def connect_poses(self, pose_a: LocalPose, pose_b: LocalPose) -> None:
        node_a = self.nearest_node(pose_a, confirmed_only=True)
        node_b = self.nearest_node(pose_b, confirmed_only=True)
        if node_a is None or node_b is None:
            return
        self.connect_nodes(node_a.node_id, node_b.node_id, pose_a.distance_to(pose_b))

    def nearest_node(
        self,
        pose: LocalPose,
        *,
        confirmed_only: bool = True,
        max_distance_m: float | None = None,
    ) -> ExplorationNode | None:
        best: ExplorationNode | None = None
        best_distance = float("inf")
        for node in self.nodes.values():
            if confirmed_only and not node.confirmed:
                continue
            distance = node.pose.planar_distance_to(pose)
            if max_distance_m is not None and distance > float(max_distance_m):
                continue
            if distance < best_distance:
                best_distance = distance
                best = node
        return best

    def distance_from_confirmed_graph(self, pose: LocalPose) -> float:
        node = self.nearest_node(pose, confirmed_only=True)
        if node is None:
            return float("inf")
        return node.pose.planar_distance_to(pose)

    def shortest_path(self, start_node_id: str, goal_node_id: str) -> list[ExplorationNode]:
        if start_node_id not in self.nodes or goal_node_id not in self.nodes:
            return []
        if start_node_id == goal_node_id:
            return [self.nodes[start_node_id]]

        distances: dict[str, float] = {start_node_id: 0.0}
        previous: dict[str, str] = {}
        remaining = set(self.nodes)

        while remaining:
            current = min(remaining, key=lambda node_id: distances.get(node_id, float("inf")))
            remaining.remove(current)
            if current == goal_node_id:
                break
            current_distance = distances.get(current, float("inf"))
            if current_distance == float("inf"):
                break
            for neighbor, weight in self.edges.get(current, {}).items():
                candidate = current_distance + float(weight)
                if candidate < distances.get(neighbor, float("inf")):
                    distances[neighbor] = candidate
                    previous[neighbor] = current

        if goal_node_id not in distances:
            return []

        order: list[str] = [goal_node_id]
        while order[-1] != start_node_id:
            order.append(previous[order[-1]])
        order.reverse()
        return [self.nodes[node_id] for node_id in order]

    def backtrack_candidates(self, *, limit: int) -> list[ExplorationNode]:
        result: list[ExplorationNode] = []
        seen: set[str] = set()
        for node_id in reversed(self.visit_order):
            if node_id in seen or node_id not in self.nodes:
                continue
            seen.add(node_id)
            node = self.nodes[node_id]
            if node.confirmed:
                result.append(node)
            if len(result) >= max(1, int(limit)):
                break
        return result


@dataclass(frozen=True)
class SkeletonBuilder:
    graph: ExplorationGraph

    def seed_from_snapshot(
        self,
        *,
        snapshot: MapSnapshot,
        dock: DockPose,
        radius_m: float,
        localization_confidence: float,
    ) -> list[ExplorationNode]:
        dock_node = self.graph.ensure_dock_node(dock)
        grid = snapshot.occupancy_grid
        dock_cell = grid.world_to_cell(dock.pose)
        max_steps = max(1, int(math.ceil(float(radius_m) / float(grid.resolution_m))))
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        nodes: list[ExplorationNode] = []

        for dx, dy in directions:
            candidate: tuple[int, int] | None = None
            for step in range(1, max_steps + 1):
                x_idx = dock_cell[0] + (dx * step)
                y_idx = dock_cell[1] + (dy * step)
                if not grid.in_bounds(x_idx, y_idx):
                    break
                if not grid.is_traversable(x_idx, y_idx, clearance_m=0.0):
                    break
                candidate = (x_idx, y_idx)
            if candidate is None:
                continue
            pose = grid.cell_to_pose(candidate[0], candidate[1], z_m=dock.pose.z_m)
            if pose.planar_distance_to(dock.pose) < max(1.0, grid.resolution_m * 2.0):
                continue
            node = self.graph.add_node(
                pose,
                confidence=float(localization_confidence),
                connected_to_dock=True,
                kind="skeleton",
            )
            self.graph.connect_nodes(
                dock_node.node_id,
                node.node_id,
                dock.pose.planar_distance_to(node.pose),
            )
            nodes.append(node)
        return nodes


@dataclass(frozen=True)
class LoopClosureScheduler:
    every_n_segments: int
    preference_weight: float = 1.0

    def should_run(self, *, segments_since_last: int, drift_estimate_m: float) -> bool:
        if segments_since_last >= max(1, int(self.every_n_segments)):
            return True
        return float(drift_estimate_m) >= float(self.preference_weight)

    def choose_target(
        self,
        *,
        graph: ExplorationGraph,
        current_pose: LocalPose,
    ) -> ExplorationNode | None:
        candidates = graph.backtrack_candidates(limit=6)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda node: node.pose.planar_distance_to(current_pose),
        )
