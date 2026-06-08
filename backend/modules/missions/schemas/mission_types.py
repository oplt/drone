from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MissionType(str, Enum):
    GRID = "grid"
    PHOTOGRAMMETRY = "photogrammetry"
    WAREHOUSE_SCAN = "warehouse_scan"
    INDOOR_EXPLORATION = "indoor_exploration"
    ORBIT = "orbit"
    TERRAIN_FOLLOW = "terrain_follow"
    PERIMETER_PATROL = "perimeter_patrol"
    PRIVATE_PATROL = "private_patrol"
    ADAPTIVE_ALTITUDE = "adaptive_altitude"
    WAYPOINT = "waypoint"
    ROUTE = "route"
    CONTROLLED = "controlled"


class Waypoint(BaseModel):
    """Waypoint model with validation."""

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: float | None = None
    altitude_msl: float | None = None
    target_agl: float | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_altitude(cls, values):
        """Ensure at least one altitude is provided."""
        alt = values.get("alt")
        alt_msl = values.get("altitude_msl")
        target_agl = values.get("target_agl")

        if alt is None and alt_msl is None and target_agl is None:
            raise ValueError("Waypoint must have at least one altitude specification")

        # Copy alt to altitude_msl if only alt is provided
        if alt is not None and alt_msl is None:
            values["altitude_msl"] = alt

        return values


class BaseMission(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    type: MissionType
    waypoints: list[Waypoint]
    speed: float | None = Field(default=10.0, ge=0.1, le=50.0)
    altitude_agl: float | None = Field(default=30.0, ge=5.0, le=500.0)


class WaypointMission(BaseMission):
    type: Literal["waypoint", "route"]


class CameraSpec(BaseModel):
    fov_h: float = Field(..., gt=0, lt=180, description="Horizontal field of view in degrees")
    fov_v: float = Field(..., gt=0, lt=180, description="Vertical field of view in degrees")
    front_overlap: float = Field(default=0.3, ge=0, le=1.0)
    side_overlap: float = Field(default=0.3, ge=0, le=1.0)

    @field_validator("fov_v")
    @classmethod
    def validate_fov(cls, v, info):
        """Ensure FOV is reasonable."""
        if "fov_h" in info.data and v > info.data["fov_h"] * 2:
            raise ValueError("Vertical FOV unusually large compared to horizontal FOV")
        return v


class GridSegment(BaseModel):
    length: float = Field(..., gt=0)
    bearing: float = Field(..., ge=-180, le=180)


class GridMission(BaseMission):
    camera: CameraSpec
    along_track_spacing: float = Field(..., gt=0, description="Spacing between images along track")
    cross_track_spacing: float = Field(..., gt=0, description="Spacing between passes")
    grid_segments: list[GridSegment] | None = None
    num_lines: int | None = Field(default=None, ge=1)

    # Legacy support
    fov: float | None = None
    line_spacing: float | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_grid(cls, values):
        """Validate grid parameters and handle legacy fields."""
        if "camera" not in values or values.get("camera") is None:
            fov = values.get("fov")
            if fov is not None:
                values["camera"] = CameraSpec(
                    fov_h=fov,
                    fov_v=fov,
                    front_overlap=values.get("front_overlap", 0.3),
                    side_overlap=values.get("side_overlap", 0.3),
                )

        # Handle legacy line_spacing
        if not values.get("cross_track_spacing") and values.get("line_spacing"):
            values["cross_track_spacing"] = values["line_spacing"]

        # Ensure along_track_spacing exists
        if not values.get("along_track_spacing") and values.get("cross_track_spacing"):
            values["along_track_spacing"] = values["cross_track_spacing"]

        return values


class OrbitMission(BaseMission):
    type: Literal["orbit", "circle", "poi"]
    radius: float = Field(..., gt=0, le=10000)
    poi_location: Waypoint | None = None
    num_orbits: int = Field(default=1, ge=1, le=100)
    direction: Literal["clockwise", "counterclockwise"] = "clockwise"
    min_standoff_m: float = Field(default=10, ge=0)

    @field_validator("radius")
    @classmethod
    def validate_radius(cls, v):
        """Ensure radius is reasonable."""
        if v < 5:
            raise ValueError("Orbit radius too small (<5m)")
        return v


class TerrainFollowMission(BaseMission):
    type: Literal["terrain_follow"]
    terrain_sample_step: float = Field(default=10, gt=0, le=500)
    min_agl: float = Field(default=10, ge=2)
    max_agl: float = Field(default=120, ge=2, le=500)
    terrain_data_source: str | None = None
    terrain_profile: list[float] | None = None

    @model_validator(mode="after")
    def validate_agl_range(self):
        """Ensure max_agl is strictly greater than min_agl."""
        if self.max_agl <= self.min_agl:
            raise ValueError(
                f"max_agl ({self.max_agl}) must be greater than min_agl ({self.min_agl})"
            )
        return self


class PerimeterPatrolMission(BaseMission):
    type: Literal["perimeter_patrol", "private_patrol", "polygon", "patrol"]
    polygon: list[Waypoint] = Field(..., min_length=3)
    path_offset_m: float = Field(default=0, ge=0)
    boundary_buffer_min: float = Field(default=10, ge=0)
    check_self_intersection: bool = True

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, v):
        """Validate polygon has at least 3 points."""
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 points")
        return v


class ControlledFlightMissionSchema(BaseMission):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
        extra="ignore",
    )
    type: Literal["controlled"]
    waypoints: list[Waypoint] = Field(default_factory=list)
    speed: float | None = Field(default=0.0, ge=0.0, le=50.0)
    altitude_agl: float | None = Field(default=30.0, ge=0.0, le=500.0)
    control_mode: str = "manual_pilot"


class AdaptiveAltitudeMission(BaseMission):
    type: Literal["adaptive_altitude"]
    target_agl: float = Field(..., gt=0, le=500)
    alt_ceiling_msl: float = Field(..., gt=0)
    alt_floor_msl: float = Field(..., ge=-500)
    agl_min: float = Field(default=5, ge=0)
    agl_max: float = Field(default=400, le=1000)

    @field_validator("alt_ceiling_msl")
    @classmethod
    def validate_ceiling(cls, v, info):
        """Ensure ceiling is above floor."""
        if "alt_floor_msl" in info.data and v <= info.data["alt_floor_msl"]:
            raise ValueError("Altitude ceiling must be above floor")
        return v

    @model_validator(mode="after")
    def validate_target_agl_within_envelope(self):
        """Ensure target_agl is within the agl_min/agl_max envelope."""
        if self.target_agl < self.agl_min:
            raise ValueError(f"target_agl ({self.target_agl}) is below agl_min ({self.agl_min})")
        if self.target_agl > self.agl_max:
            raise ValueError(f"target_agl ({self.target_agl}) exceeds agl_max ({self.agl_max})")
        return self


class PhotogrammetryMission(BaseMission):
    type: Literal["photogrammetry"]
    polygon: list[Waypoint] = Field(..., min_length=3)
    altitude_agl: float = Field(default=30.0, ge=10.0, le=120.0)
    front_overlap: float = Field(default=0.8, ge=0.5, le=0.95)
    side_overlap: float = Field(default=0.7, ge=0.5, le=0.95)
    min_spacing_m: float = Field(default=0.5, gt=0.0, le=10.0)
    camera_fov_h: float = Field(default=78.0, gt=0, lt=180)
    camera_fov_v: float = Field(default=62.0, gt=0, lt=180)
    max_flight_time_min: float | None = None


class WarehouseLocalPoint(BaseModel):
    x_m: float
    y_m: float
    z_m: float = 0.0


class WarehouseLocalOrigin(BaseModel):
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    alt_m: float = 0.0

    @model_validator(mode="after")
    def validate_coordinate_pair(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError(
                "Warehouse local_origin lat and lon must both be set or both be omitted"
            )
        return self


# Indoor/sim warehouse scans use a pure local metric frame (no GPS tie-in).
# Dock pose is configured separately via warehouse map dock stations.
SIM_WAREHOUSE_LOCAL_ORIGIN = WarehouseLocalOrigin(alt_m=0.0)


class WarehouseCorridor(BaseModel):
    corridor_id: str = Field(..., min_length=1, max_length=128)
    start: WarehouseLocalPoint
    end: WarehouseLocalPoint
    width_m: float = Field(..., gt=0.0, le=100.0)
    heading_deg: float = Field(..., ge=-180.0, le=360.0)
    axis_deg: float = Field(..., ge=-180.0, le=360.0)
    source: str = Field(default="derived", min_length=1, max_length=64)


class WarehouseObstacleBox(BaseModel):
    obstacle_id: str = Field(..., min_length=1, max_length=128)
    center: WarehouseLocalPoint
    size_x_m: float = Field(..., gt=0.0, le=500.0)
    size_y_m: float = Field(..., gt=0.0, le=500.0)
    size_z_m: float = Field(..., gt=0.0, le=500.0)


class WarehouseKeepoutZone(BaseModel):
    zone_id: str = Field(..., min_length=1, max_length=128)
    footprint: list[WarehouseLocalPoint] = Field(..., min_length=3)
    min_z_m: float | None = None
    max_z_m: float | None = None

    @model_validator(mode="after")
    def validate_z_range(self):
        if self.min_z_m is not None and self.max_z_m is not None and self.max_z_m <= self.min_z_m:
            raise ValueError("max_z_m must be greater than min_z_m")
        return self


class WarehouseScanLayer(BaseModel):
    layer_index: int = Field(..., ge=0, le=100)
    label: str = Field(..., min_length=1, max_length=64)
    z_m: float = Field(..., ge=0.0, le=500.0)


class WarehouseScanMission(BaseMission):
    type: Literal["warehouse_scan"]
    waypoints: list[Waypoint] = Field(default_factory=list)
    polygon: list[Waypoint] = Field(default_factory=list)
    speed: float | None = Field(default=0.8, gt=0.0, le=50.0)
    altitude_agl: float | None = Field(default=None, ge=0.0, le=500.0)
    local_origin: WarehouseLocalOrigin | None = None
    sensor_rig_id: int | None = Field(default=None, ge=1)
    dock_marker_id: str | None = Field(default=None, max_length=128)
    dock_precision_required: bool = False
    local_polygon: list[WarehouseLocalPoint] = Field(..., min_length=3)
    corridors: list[WarehouseCorridor] = Field(default_factory=list)
    obstacles_3d: list[WarehouseObstacleBox] = Field(default_factory=list)
    keepout_zones: list[WarehouseKeepoutZone] = Field(default_factory=list)
    scan_layers: list[WarehouseScanLayer] = Field(default_factory=list, min_length=1)
    corridor_spacing_m: float = Field(default=2.0, gt=0.1, le=50.0)
    aisle_axis_deg: float | None = Field(default=None, ge=-180.0, le=360.0)
    clearance_m: float = Field(default=0.6, gt=0.1, le=20.0)
    perimeter_offset_m: float = Field(default=0.5, ge=0.0, le=20.0)
    scan_pattern: Literal[
        "aisle_serpentine",
        "stacked_passes",
        "crosshatch",
        "perimeter_aisle_hybrid",
    ] = "aisle_serpentine"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    view_mode: Literal["forward", "left_face", "right_face", "dual_face"] = "forward"
    layer_count: int = Field(default=1, ge=1, le=20)
    layer_spacing_m: float = Field(default=1.2, ge=0.0, le=20.0)
    ceiling_height_m: float | None = Field(default=8.0, gt=0.0, le=100.0)
    ceiling_margin_m: float = Field(default=0.7, ge=0.0, le=20.0)
    work_speed_mps: float = Field(default=0.8, gt=0.0, le=20.0)
    transit_speed_mps: float = Field(default=1.4, gt=0.0, le=30.0)
    scan_pause_s: float = Field(default=0.0, ge=0.0, le=30.0)
    interpolate_steps_work_leg: int = Field(default=4, ge=0, le=100)
    interpolate_steps_transit_leg: int = Field(default=1, ge=0, le=100)
    local_control_mode: Literal["local_setpoint"] = "local_setpoint"


class IndoorLocalPose(BaseModel):
    x_m: float
    y_m: float
    z_m: float = 0.0
    yaw_deg: float | None = Field(default=None, ge=-180.0, le=360.0)
    frame_id: str = Field(default="map", min_length=1, max_length=32)


class IndoorDockPose(BaseModel):
    dock_id: str = Field(..., min_length=1, max_length=128)
    pose: IndoorLocalPose
    entry_pose: IndoorLocalPose
    exit_pose: IndoorLocalPose
    marker_id: str | None = Field(default=None, max_length=128)
    precision_required: bool = True


class IndoorExplorationMission(BaseMission):
    type: Literal["indoor_exploration"]
    waypoints: list[Waypoint] = Field(default_factory=list)
    speed: float | None = Field(default=0.8, gt=0.0, le=20.0)
    altitude_agl: float | None = Field(default=None, ge=0.0, le=500.0)
    dock: IndoorDockPose
    safe_takeoff_bubble_radius_m: float = Field(default=1.5, gt=0.1, le=20.0)
    battery_return_reserve_pct: float = Field(default=30.0, ge=5.0, le=95.0)
    battery_emergency_land_reserve_pct: float = Field(default=20.0, ge=5.0, le=95.0)
    localization_confidence_min: float = Field(default=0.65, ge=0.0, le=1.0)
    localization_confidence_return_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    obstacle_clearance_m: float = Field(default=0.8, gt=0.1, le=20.0)
    minimum_corridor_clearance_m: float = Field(default=1.0, gt=0.1, le=20.0)
    max_mission_time_s: float = Field(default=900.0, gt=10.0, le=86_400.0)
    max_exploration_radius_m: float = Field(default=80.0, gt=1.0, le=2_000.0)
    max_path_length_m: float = Field(default=600.0, gt=1.0, le=10_000.0)
    frontier_min_gain: float = Field(default=1.0, ge=0.0, le=1_000.0)
    skeleton_build_radius_m: float = Field(default=12.0, gt=0.5, le=500.0)
    force_loop_closure_every_n_segments: int = Field(default=3, ge=1, le=100)
    max_unknown_penetration_m: float = Field(default=2.0, ge=0.0, le=100.0)
    dock_search_radius_m: float = Field(default=1.5, gt=0.1, le=25.0)
    dock_approach_speed_mps: float = Field(default=0.3, gt=0.05, le=5.0)
    dock_descent_speed_mps: float = Field(default=0.15, gt=0.01, le=2.0)
    docking_timeout_s: float = Field(default=90.0, gt=5.0, le=3_600.0)
    occupancy_resolution_m: float = Field(default=0.5, gt=0.05, le=5.0)
    map_update_hz: float = Field(default=2.0, gt=0.1, le=50.0)
    loop_closure_preference_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    backtrack_node_limit: int = Field(default=6, ge=1, le=100)
    local_control_mode: Literal["local_setpoint"] = "local_setpoint"

    @model_validator(mode="after")
    def validate_reserves(self) -> "IndoorExplorationMission":
        if self.battery_return_reserve_pct <= self.battery_emergency_land_reserve_pct:
            raise ValueError(
                "battery_return_reserve_pct must be greater than battery_emergency_land_reserve_pct"
            )
        return self


Mission = Annotated[
    WaypointMission
    | GridMission
    | PhotogrammetryMission
    | WarehouseScanMission
    | IndoorExplorationMission
    | OrbitMission
    | TerrainFollowMission
    | PerimeterPatrolMission
    | AdaptiveAltitudeMission
    | ControlledFlightMissionSchema,
    Field(discriminator="type"),
]


def create_mission_from_dict(data: dict) -> Mission:
    mission_type = data.get("type", "").lower()

    type_map = {
        "waypoint": WaypointMission,
        "route": WaypointMission,
        "grid": GridMission,
        "survey": GridMission,
        "photogrammetry": PhotogrammetryMission,
        "warehouse_scan": WarehouseScanMission,
        "indoor_exploration": IndoorExplorationMission,
        "orbit": OrbitMission,
        "circle": OrbitMission,
        "poi": OrbitMission,
        "terrain_follow": TerrainFollowMission,
        "perimeter_patrol": PerimeterPatrolMission,
        "private_patrol": PerimeterPatrolMission,
        "polygon": PerimeterPatrolMission,
        "patrol": PerimeterPatrolMission,
        "adaptive_altitude": AdaptiveAltitudeMission,
        "controlled": ControlledFlightMissionSchema,
    }

    mission_class = type_map.get(mission_type)
    if mission_class is None:
        raise ValueError(f"Unknown mission type: {mission_type}")

    return mission_class(**data)
