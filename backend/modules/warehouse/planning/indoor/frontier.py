from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from .models import Frontier, LocalPose, MapSnapshot, OccupancyGrid
from .skeleton_graph import ExplorationGraph


@dataclass(frozen=True)
class FrontierScoreWeights:
    information_gain: float = 2.2
    path_length: float = 0.05
    clearance: float = 1.2
    localization: float = 1.6
    drift: float = 1.0
    return_graph: float = 0.08
    battery: float = 0.9
    corridor: float = 1.4
    loop_closure_bias: float = 0.6


class FrontierExtractor:
    def __init__(self, *, obstacle_clearance_m: float, minimum_corridor_clearance_m: float):
        self.obstacle_clearance_m = float(obstacle_clearance_m)
        self.minimum_corridor_clearance_m = float(minimum_corridor_clearance_m)

    def extract(
        self,
        *,
        snapshot: MapSnapshot,
        current_pose: LocalPose,
        graph: ExplorationGraph,
        localization_confidence: float,
    ) -> list[Frontier]:
        grid = snapshot.occupancy_grid
        frontiers: list[Frontier] = []
        for index, group in enumerate(grid.frontier_groups()):
            centroid = self._centroid_pose(grid, group, z_m=current_pose.z_m)
            approach = self._approach_pose(grid, centroid, z_m=current_pose.z_m)
            if approach is None:
                continue
            path = grid.astar_path(
                current_pose,
                approach,
                clearance_m=self.obstacle_clearance_m,
            )
            if not path:
                continue
            path_length_m = OccupancyGrid.path_length_m(path)
            clearance_m = grid.clearance_at(approach)
            if clearance_m < self.minimum_corridor_clearance_m:
                continue
            return_graph_distance_m = graph.distance_from_confirmed_graph(approach)
            information_gain = float(len(group)) * (float(grid.resolution_m) ** 2)
            drift_penalty = max(0.0, path_length_m / 30.0)
            corridor_preference = max(
                0.0,
                1.0 - (return_graph_distance_m / max(1.0, path_length_m + 1.0)),
            )
            frontiers.append(
                Frontier(
                    frontier_id=f"frontier_{index}",
                    centroid=centroid,
                    approach_pose=approach,
                    cell_count=len(group),
                    information_gain=information_gain,
                    path_length_m=path_length_m,
                    clearance_m=clearance_m,
                    localization_confidence=float(localization_confidence),
                    drift_penalty=drift_penalty,
                    return_graph_distance_m=return_graph_distance_m,
                    battery_cost_pct=0.0,
                    corridor_preference=corridor_preference,
                    metadata={"cells": list(group)},
                )
            )
        return frontiers

    @staticmethod
    def _centroid_pose(
        grid: OccupancyGrid,
        cells: Iterable[tuple[int, int]],
        *,
        z_m: float,
    ) -> LocalPose:
        cell_list = list(cells)
        mean_x = sum(float(cell[0]) for cell in cell_list) / max(1, len(cell_list))
        mean_y = sum(float(cell[1]) for cell in cell_list) / max(1, len(cell_list))
        return grid.cell_to_pose(int(round(mean_x)), int(round(mean_y)), z_m=z_m)

    @staticmethod
    def _approach_pose(
        grid: OccupancyGrid,
        centroid: LocalPose,
        *,
        z_m: float,
    ) -> LocalPose | None:
        nearest = grid.nearest_free_cell(centroid, clearance_m=0.0, max_radius_m=2.0)
        if nearest is None:
            return None
        return grid.cell_to_pose(nearest[0], nearest[1], z_m=z_m)


class FrontierScorer:
    def __init__(self, weights: FrontierScoreWeights | None = None):
        self.weights = weights or FrontierScoreWeights()

    def score(
        self,
        frontier: Frontier,
        *,
        skeleton_phase: bool,
        loop_closure_due: bool,
    ) -> Frontier:
        score = 0.0
        score += self.weights.information_gain * float(frontier.information_gain)
        score -= self.weights.path_length * float(frontier.path_length_m)
        score += self.weights.clearance * float(frontier.clearance_m)
        score += self.weights.localization * float(frontier.localization_confidence)
        score -= self.weights.drift * float(frontier.drift_penalty)
        score -= self.weights.return_graph * float(frontier.return_graph_distance_m)
        score -= self.weights.battery * float(frontier.battery_cost_pct)
        corridor_bonus = float(frontier.corridor_preference)
        if skeleton_phase:
            corridor_bonus *= 2.0
        score += self.weights.corridor * corridor_bonus
        if loop_closure_due:
            score -= self.weights.loop_closure_bias * float(frontier.path_length_m)
        return replace(frontier, score=score)


class FrontierSelector:
    def __init__(self, *, strategy: str = "weighted_score"):
        self.strategy = strategy

    def rank(
        self,
        frontiers: list[Frontier],
        *,
        max_candidates: int,
    ) -> list[Frontier]:
        ranked = sorted(frontiers, key=lambda frontier: frontier.score, reverse=True)
        return ranked[: max(1, int(max_candidates))]
