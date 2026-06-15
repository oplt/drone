from __future__ import annotations

import heapq
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
        self.obstacle_clearance_m = max(0.0, float(obstacle_clearance_m))
        self.minimum_corridor_clearance_m = max(0.0, float(minimum_corridor_clearance_m))

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
        resolution_sq_m = float(grid.resolution_m) ** 2
        groups = grid.frontier_groups()
        for index, group in enumerate(groups):
            if not group:
                continue
            centroid = self._centroid_pose(grid, group, z_m=current_pose.z_m)
            approach = self._approach_pose(
                grid,
                centroid,
                z_m=current_pose.z_m,
                clearance_m=self.obstacle_clearance_m,
            )
            if approach is None:
                continue
            clearance_m = grid.clearance_at(approach)
            if clearance_m < self.minimum_corridor_clearance_m:
                continue

            # A* is the expensive step, so run it only after cheap geometric
            # filters prove that this frontier is actually usable.
            path = grid.astar_path(
                current_pose,
                approach,
                clearance_m=self.obstacle_clearance_m,
            )
            if not path:
                continue

            path_length_m = OccupancyGrid.path_length_m(path)
            return_graph_distance_m = graph.distance_from_confirmed_graph(approach)
            information_gain = float(len(group)) * resolution_sq_m
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
                    metadata={"cells": tuple(group)},
                )
            )
        return frontiers

    @staticmethod
    def _centroid_pose(
        grid: OccupancyGrid,
        cells: list[tuple[int, int]],
        *,
        z_m: float,
    ) -> LocalPose:
        if not cells:
            return grid.cell_to_pose(0, 0, z_m=z_m)
        inv_count = 1.0 / float(len(cells))
        mean_x = sum(cell[0] for cell in cells) * inv_count
        mean_y = sum(cell[1] for cell in cells) * inv_count
        return grid.cell_to_pose(int(round(mean_x)), int(round(mean_y)), z_m=z_m)

    @staticmethod
    def _approach_pose(
        grid: OccupancyGrid,
        centroid: LocalPose,
        *,
        z_m: float,
        clearance_m: float,
    ) -> LocalPose | None:
        nearest = grid.nearest_free_cell(
            centroid,
            clearance_m=max(0.0, float(clearance_m)),
            max_radius_m=2.0,
        )
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
        limit = int(max_candidates)
        if limit <= 0 or not frontiers:
            return []
        if limit >= len(frontiers):
            return sorted(frontiers, key=lambda frontier: frontier.score, reverse=True)
        return heapq.nlargest(limit, frontiers, key=lambda frontier: frontier.score)
