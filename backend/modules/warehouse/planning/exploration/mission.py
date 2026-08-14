from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, model_validator

from backend.modules.missions.flight_models import FlightStatus
from backend.modules.vehicle_runtime.types import Coordinate
from backend.modules.warehouse.planning.indoor import (
    DockingController,
    DockPose,
    DroneLocalNavigationAdapter,
    Frontier,
    FrontierExtractor,
    FrontierScorer,
    FrontierSelector,
    IndoorMissionState,
    LocalNavigationAdapter,
    LocalPose,
    LoopClosureScheduler,
    PrecisionDockingController,
    ReturnMarginEstimate,
    ReturnMarginEvaluator,
    SimulatedLocalNavigationAdapter,
    SimulatedSLAMProvider,
    SkeletonBuilder,
    SLAMHealth,
    SLAMProvider,
)
from backend.modules.warehouse.planning.mission import (
    WarehouseDockConfigParams,
    WarehouseDockPoseParams,
)
from backend.modules.warehouse.service.safety import (
    WarehouseSafetyDecision,
    evaluate_warehouse_runtime_safety,
)

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator
    from backend.modules.warehouse.planning.indoor import ExplorationGraph, MapSnapshot, SLAMHealth

logger = logging.getLogger(__name__)



from backend.modules.warehouse.planning.exploration.bootstrap import WarehouseExplorationBootstrapMixin
from backend.modules.warehouse.planning.exploration.fly_exploration import WarehouseExplorationFlyMixin
from backend.modules.warehouse.planning.exploration.fly_exploration_complete import (
    WarehouseExplorationFlyCompleteMixin,
)
from backend.modules.warehouse.planning.exploration.fly_exploration_teardown import (
    WarehouseExplorationFlyTeardownMixin,
)
from backend.modules.warehouse.planning.exploration.frontier import WarehouseExplorationFrontierMixin
from backend.modules.warehouse.planning.exploration.graph_nodes import WarehouseExplorationGraphMixin
from backend.modules.warehouse.planning.exploration.localization import WarehouseExplorationLocalizationMixin
from backend.modules.warehouse.planning.exploration.loop_closure import WarehouseExplorationLoopClosureMixin
from backend.modules.warehouse.planning.exploration.persistence import WarehouseExplorationPersistenceMixin
from backend.modules.warehouse.planning.exploration.providers import WarehouseExplorationProvidersMixin
from backend.modules.warehouse.planning.exploration.return_dock import WarehouseExplorationReturnDockMixin
from backend.modules.warehouse.planning.exploration.safety import WarehouseExplorationSafetyMixin
from backend.modules.warehouse.planning.exploration.serializers import WarehouseExplorationSerializersMixin
from backend.modules.warehouse.planning.exploration.status import WarehouseExplorationStatusMixin

@dataclass
class UnknownWarehouseExplorationMission(
    WarehouseExplorationFlyMixin,
    WarehouseExplorationFlyTeardownMixin,
    WarehouseExplorationFlyCompleteMixin,
    WarehouseExplorationProvidersMixin,
    WarehouseExplorationBootstrapMixin,
    WarehouseExplorationStatusMixin,
    WarehouseExplorationSafetyMixin,
    WarehouseExplorationGraphMixin,
    WarehouseExplorationFrontierMixin,
    WarehouseExplorationLoopClosureMixin,
    WarehouseExplorationLocalizationMixin,
    WarehouseExplorationReturnDockMixin,
    WarehouseExplorationPersistenceMixin,
    WarehouseExplorationSerializersMixin,):
    dock: DockPose
    warehouse_map_id: int | None = None
    warehouse_name: str | None = None
    owner_id: int | None = None

    indoor_hover_alt_m: float = 2.5
    frontier_selection_strategy: str = "weighted_score"
    max_mission_time_s: float = 900.0
    max_exploration_radius_m: float = 80.0
    max_path_length_m: float = 600.0
    frontier_min_gain: float = 1.0
    frontier_reach_timeout_s: float = 60.0
    skeleton_build_radius_m: float = 12.0
    max_frontier_candidates: int = 8
    force_loop_closure_every_n_segments: int = 3
    max_unknown_penetration_m: float = 2.0
    minimum_corridor_clearance_m: float = 1.0
    battery_return_reserve_pct: float = 30.0
    battery_emergency_land_reserve_pct: float = 20.0
    localization_confidence_min: float = 0.65
    localization_confidence_return_threshold: float = 0.5
    obstacle_clearance_m: float = 0.8
    relocalization_timeout_s: float = 15.0
    backtrack_node_limit: int = 6
    safe_takeoff_bubble_radius_m: float = 1.5
    dock_pose_name: str = "dock"
    dock_search_radius_m: float = 1.5
    dock_approach_speed_mps: float = 0.3
    dock_descent_speed_mps: float = 0.15
    docking_timeout_s: float = 90.0
    occupancy_resolution_m: float = 0.5
    voxel_resolution_m: float | None = None
    map_update_hz: float = 2.0
    map_snapshot_interval_s: float = 5.0
    loop_closure_preference_weight: float = 1.0
    explore_speed_mps: float = 0.8
    transit_speed_mps: float = 1.1

    slam_provider: SLAMProvider | None = field(default=None, repr=False, compare=False)
    navigator: LocalNavigationAdapter | None = field(default=None, repr=False, compare=False)
    dock_controller: DockingController | None = field(default=None, repr=False, compare=False)

    mission_type: str = field(default="indoor_exploration", init=False)
    _state: IndoorMissionState = field(
        default=IndoorMissionState.IDLE_AT_DOCK, init=False, repr=False
    )
    _state_history: list[IndoorMissionState] = field(default_factory=list, init=False, repr=False)
    _graph: ExplorationGraph | None = field(default=None, init=False, repr=False)
    _mission_started_at: float = field(default=0.0, init=False, repr=False)
    _last_snapshot_event_at: float = field(default=0.0, init=False, repr=False)
    _segments_completed: int = field(default=0, init=False, repr=False)
    _docked_successfully: bool = field(default=False, init=False, repr=False)

    @property
    def state_history(self) -> list[str]:
        return [state.value for state in self._state_history]

    def get_waypoints(self) -> list[Coordinate]:
        return []

    def get_flight_record_anchor(self, alt: float) -> tuple[Coordinate, Coordinate, str]:
        placeholder = Coordinate(lat=0.0, lon=0.0, alt=float(alt))
        return placeholder, placeholder, "indoor_local_placeholder"

    def get_preflight_mission_data(self) -> dict[str, object]:
        dock = self.dock
        return {
            "type": "indoor_exploration",
            "waypoints": [],
            "speed": float(self.transit_speed_mps),
            "altitude_agl": float(self.indoor_hover_alt_m),
            "dock": {
                "dock_id": dock.dock_id,
                "pose": self._pose_dict(dock.pose),
                "entry_pose": self._pose_dict(dock.entry_pose),
                "exit_pose": self._pose_dict(dock.exit_pose),
                "marker_id": dock.marker_id,
                "precision_required": bool(dock.precision_required),
            },
            "safe_takeoff_bubble_radius_m": float(self.safe_takeoff_bubble_radius_m),
            "battery_return_reserve_pct": float(self.battery_return_reserve_pct),
            "battery_emergency_land_reserve_pct": float(self.battery_emergency_land_reserve_pct),
            "localization_confidence_min": float(self.localization_confidence_min),
            "localization_confidence_return_threshold": float(
                self.localization_confidence_return_threshold
            ),
            "obstacle_clearance_m": float(self.obstacle_clearance_m),
            "minimum_corridor_clearance_m": float(self.minimum_corridor_clearance_m),
            "max_mission_time_s": float(self.max_mission_time_s),
            "max_exploration_radius_m": float(self.max_exploration_radius_m),
            "max_path_length_m": float(self.max_path_length_m),
            "frontier_min_gain": float(self.frontier_min_gain),
            "skeleton_build_radius_m": float(self.skeleton_build_radius_m),
            "force_loop_closure_every_n_segments": int(self.force_loop_closure_every_n_segments),
            "max_unknown_penetration_m": float(self.max_unknown_penetration_m),
            "dock_search_radius_m": float(self.dock_search_radius_m),
            "dock_approach_speed_mps": float(self.dock_approach_speed_mps),
            "dock_descent_speed_mps": float(self.dock_descent_speed_mps),
            "docking_timeout_s": float(self.docking_timeout_s),
            "occupancy_resolution_m": float(self.occupancy_resolution_m),
            "map_update_hz": float(self.map_update_hz),
            "loop_closure_preference_weight": float(self.loop_closure_preference_weight),
            "backtrack_node_limit": int(self.backtrack_node_limit),
            "local_control_mode": "local_setpoint",
        }

    async def execute(self, orch: Orchestrator, *, alt: float = 2.5) -> None:
        if not math.isclose(float(alt), float(self.indoor_hover_alt_m), abs_tol=1e-6):
            self.indoor_hover_alt_m = float(alt)
        await orch.run_mission(
            self,
            alt=float(self.indoor_hover_alt_m),
            flight_fn=lambda: self.fly_exploration(orch),
        )
