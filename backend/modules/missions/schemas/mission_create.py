from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.modules.missions.flight_profile import FlightEnvironment
from backend.modules.missions.schemas.mission_types import MissionType, Waypoint
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS


class GridMissionParams(BaseModel):
    """Parameters for a GridMission (polygon-driven lawnmower)."""

    # [[lon, lat], …] – GeoJSON coordinate order
    field_polygon_lonlat: list[list[float]] = Field(
        ..., min_length=3, description="Polygon ring as [[lon, lat], …]"
    )
    row_spacing_m: float = Field(default=7.5, gt=0, le=200)
    grid_angle_deg: float | None = Field(default=None, ge=0, lt=180)
    slope_aware: bool = False
    safety_inset_m: float = Field(default=1.5, ge=0)
    terrain_follow: bool = False
    agl_m: float = Field(default=30.0, gt=0)
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = Field(default=90.0, gt=0, lt=180)
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    row_stride: int = Field(default=1, ge=1, le=20)
    row_phase_m: float = Field(default=0.0, ge=0.0, le=500.0)


PatrolTaskType = Literal[
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
]


def validate_private_patrol_task_inputs(
    *,
    task_type: str,
    property_polygon_lonlat: list[list[float]] | None,
    key_points_lonlat: list[list[float]] | None,
) -> None:
    if task_type in {"perimeter_patrol", "grid_surveillance"}:
        if not property_polygon_lonlat or len(property_polygon_lonlat) < 3:
            raise ValueError(
                f"task_type='{task_type}' requires property_polygon_lonlat with at least 3 coordinate pairs."
            )
    elif task_type == "waypoint_patrol":
        if not key_points_lonlat or len(key_points_lonlat) < 2:
            raise ValueError(
                "task_type='waypoint_patrol' requires key_points_lonlat with at least 2 coordinate pairs."
            )
    elif task_type == "event_triggered_patrol":
        if not property_polygon_lonlat or len(property_polygon_lonlat) < 3:
            raise ValueError(
                "task_type='event_triggered_patrol' requires property_polygon_lonlat geofence."
            )


class PrivatePatrolMissionParams(BaseModel):
    """Parameters for private patrol missions."""

    task_type: Literal[
        "perimeter_patrol",
        "waypoint_patrol",
        "grid_surveillance",
        "event_triggered_patrol",
    ] = "perimeter_patrol"
    property_polygon_lonlat: list[list[float]] | None = Field(
        default=None,
        min_length=3,
        description="Perimeter/Grid mode: property polygon ring as [[lon, lat], ...]",
    )
    key_points_lonlat: list[list[float]] | None = Field(
        default=None,
        min_length=2,
        description="Waypoint mode: ordered key points as [[lon, lat], ...]",
    )
    path_offset_m: float = Field(default=15.0, ge=0.0, le=120.0)
    direction: Literal["clockwise", "counterclockwise"] = "clockwise"
    patrol_loops: int = Field(default=1, ge=1, le=200)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    start_after_minutes: int = Field(default=0, ge=0, le=1440)
    repeat_interval_minutes: int = Field(default=0, ge=0, le=1440)
    camera_angle_deg: float = Field(default=35.0, ge=0.0, le=90.0)
    camera_overlap_pct: float = Field(default=50.0, ge=0.0, le=95.0)
    max_segment_length_m: float = Field(default=20.0, gt=1.0, le=300.0)
    hover_time_s: float = Field(default=15.0, ge=1.0, le=300.0)
    camera_scan_yaw_deg: float = Field(default=360.0, ge=0.0, le=360.0)
    zoom_capture: bool = True
    return_to_start: bool = True
    grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    grid_angle_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    safety_inset_m: float = Field(default=2.0, ge=0.0, le=100.0)
    grid_pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    grid_crosshatch_angle_offset_deg: float = Field(default=90.0, gt=0.0, lt=180.0)
    grid_lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    grid_start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    grid_row_stride: int = Field(default=1, ge=1, le=20)
    grid_row_phase_m: float = Field(default=0.0, ge=0.0, le=500.0)
    trigger_event_location_lonlat: list[float] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Event task: trigger location as [lon, lat]",
    )
    target_label: str | None = Field(default=None, max_length=120)
    verification_loiter_s: float = Field(default=45.0, ge=0.0, le=600.0)
    verification_radius_m: float = Field(default=18.0, ge=0.0, le=150.0)
    track_target: bool = True
    auto_stream_video: bool = True
    record_video_stream: bool = True
    ai_tasks: list[PatrolTaskType] = Field(default_factory=lambda: list(PATROL_AI_TASKS))

    @model_validator(mode="after")
    def _validate_by_task(self) -> PrivatePatrolMissionParams:
        validate_private_patrol_task_inputs(
            task_type=self.task_type,
            property_polygon_lonlat=self.property_polygon_lonlat,
            key_points_lonlat=self.key_points_lonlat,
        )
        return self


class MissionProfileCamera(BaseModel):
    orientation: Literal["nadir"] = "nadir"
    fixed_exposure: bool = True
    fov_h_deg: float = Field(default=78.0, gt=1.0, lt=179.0)
    fov_v_deg: float = Field(default=62.0, gt=1.0, lt=179.0)


class MissionProfileTriggerDistance(BaseModel):
    mode: Literal["distance"] = "distance"
    distance_m: float = Field(default=2.5, gt=0.1, le=50.0)


class MissionProfileTriggerTime(BaseModel):
    mode: Literal["time"] = "time"
    interval_s: float = Field(default=1.0, gt=0.1, le=30.0)


MissionProfileTrigger = Annotated[
    MissionProfileTriggerDistance | MissionProfileTriggerTime,
    Field(discriminator="mode"),
]


class PhotogrammetryMissionProfile(BaseModel):
    type: Literal["photogrammetry"] = "photogrammetry"
    altitude_m: float = Field(default=25.0, ge=20.0, le=30.0)
    front_overlap_pct: float = Field(default=80.0, ge=75.0, le=85.0)
    side_overlap_pct: float = Field(default=70.0, ge=65.0, le=75.0)
    min_spacing_m: float = Field(default=0.5, gt=0.0, le=10.0)
    speed_mps: float = Field(default=3.0, gt=0.1, le=20.0)
    trigger: MissionProfileTrigger = Field(default_factory=MissionProfileTriggerDistance)
    accuracy: Literal["standard_gnss", "rtk_ppk"] = "rtk_ppk"
    camera: MissionProfileCamera = Field(default_factory=MissionProfileCamera)


class MissionCreateIn(BaseModel):
    """
    Unified mission creation payload.

    For `mission_type = "waypoints"`: supply `waypoints` (≥ 2).
    For `mission_type = "grid"`:     supply `grid` params with polygon.
    For `mission_type = "perimeter_patrol"` / `"private_patrol"`:
        supply `private_patrol` params:
          - perimeter task uses `property_polygon_lonlat`
          - waypoint task uses `key_points_lonlat`
          - grid task uses `property_polygon_lonlat` + grid parameters
    """

    name: str = Field(default="mission", min_length=1, max_length=120)
    cruise_alt: float = Field(default=30.0, gt=0, le=500)
    mission_type: MissionType = MissionType.WAYPOINT
    flight_environment: FlightEnvironment | None = Field(
        default=None,
        description=(
            "Optional control profile override. Use indoor_local only for warehouse/local-frame "
            "missions; default is derived from mission_type."
        ),
    )

    # Waypoints mission data
    waypoints: list[Waypoint] | None = None

    # Grid mission data
    grid: GridMissionParams | None = None
    private_patrol: PrivatePatrolMissionParams | None = None
    warehouse_scan: Any | None = None
    warehouse_inspection: Any | None = None
    mission_profile: PhotogrammetryMissionProfile | None = None
    preflight_run_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        description=(
            "Optional preflight run token from POST /tasks/preflight/run. "
            "When provided, mission start validates that token against this payload."
        ),
    )

    @model_validator(mode="after")
    def _check_payload(self) -> MissionCreateIn:
        if self.mission_type == MissionType.CONTROLLED:
            pass  # no extra params required
        elif self.mission_type == MissionType.WAYPOINT:
            if not self.waypoints or len(self.waypoints) < 2:
                raise ValueError("mission_type='waypoints' requires at least 2 waypoints.")
        elif self.mission_type in {MissionType.GRID, MissionType.PHOTOGRAMMETRY}:
            if self.grid is None:
                raise ValueError("mission_type requires a 'grid' object with field_polygon_lonlat.")
            if len(self.grid.field_polygon_lonlat) < 3:
                raise ValueError("field_polygon_lonlat must have at least 3 coordinate pairs.")
        elif self.mission_type in {
            MissionType.WAREHOUSE_SCAN,
            MissionType.WAREHOUSE_INSPECTION,
            MissionType.INDOOR_EXPLORATION,
        }:
            if self.mission_type == MissionType.WAREHOUSE_SCAN:
                if self.warehouse_scan is None:
                    raise ValueError(
                        "mission_type='warehouse_scan' requires a 'warehouse_scan' object."
                    )
            elif self.mission_type == MissionType.WAREHOUSE_INSPECTION:
                if self.warehouse_inspection is None:
                    raise ValueError(
                        "mission_type='warehouse_inspection' requires a 'warehouse_inspection' object."
                    )
            elif self.warehouse_scan is None:
                raise ValueError(
                    "mission_type='indoor_exploration' requires warehouse_scan exploration params."
                )
        elif self.mission_type in {
            MissionType.PERIMETER_PATROL,
            MissionType.PRIVATE_PATROL,
        }:
            if self.private_patrol is None:
                raise ValueError(
                    "mission_type='perimeter_patrol' requires a 'private_patrol' object."
                )
        if self.mission_profile is not None and self.mission_type not in {
            MissionType.GRID,
            MissionType.PHOTOGRAMMETRY,
        }:
            raise ValueError(
                "mission_profile is supported only for mission_type='grid' or 'photogrammetry'."
            )
        return self


class MissionCreateOut(BaseModel):
    flight_id: str
    status: str
    mission_name: str
    mission_type: str
    waypoints_count: int
    preflight_run_id: str | None = None
