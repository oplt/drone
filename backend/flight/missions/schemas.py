from typing import List, Optional, Union, Literal, Annotated
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from enum import Enum
from math import tan, radians


class MissionType(str, Enum):
    GRID = "grid"
    PHOTOGRAMMETRY = "photogrammetry"
    ORBIT = "orbit"
    TERRAIN_FOLLOW = "terrain_follow"
    PERIMETER_PATROL = "perimeter_patrol"
    PRIVATE_PATROL = "private_patrol"
    ADAPTIVE_ALTITUDE = "adaptive_altitude"
    WAYPOINT = "waypoint"
    ROUTE = "route"


class Waypoint(BaseModel):
    """Waypoint model with validation."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: Optional[float] = None
    altitude_msl: Optional[float] = None
    target_agl: Optional[float] = None


    @model_validator(mode='before')
    @classmethod
    def validate_altitude(cls, values):
        """Ensure at least one altitude is provided."""
        alt = values.get('alt')
        alt_msl = values.get('altitude_msl')
        target_agl = values.get('target_agl')

        if alt is None and alt_msl is None and target_agl is None:
            raise ValueError("Waypoint must have at least one altitude specification")

        # Copy alt to altitude_msl if only alt is provided
        if alt is not None and alt_msl is None:
            values['altitude_msl'] = alt

        return values


class BaseMission(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    type: MissionType
    waypoints: List[Waypoint]
    speed: Optional[float] = Field(default=10.0, ge=0.1, le=50.0)
    altitude_agl: Optional[float] = Field(default=30.0, ge=5.0, le=500.0)


class WaypointMission(BaseMission):
    type: Literal["waypoint", "route"]


class CameraSpec(BaseModel):
    fov_h: float = Field(..., gt=0, lt=180, description="Horizontal field of view in degrees")
    fov_v: float = Field(..., gt=0, lt=180, description="Vertical field of view in degrees")
    front_overlap: float = Field(default=0.3, ge=0, le=1.0)
    side_overlap: float = Field(default=0.3, ge=0, le=1.0)

    @field_validator('fov_v')
    @classmethod
    def validate_fov(cls, v, info):
        """Ensure FOV is reasonable."""
        if 'fov_h' in info.data and v > info.data['fov_h'] * 2:
            raise ValueError("Vertical FOV unusually large compared to horizontal FOV")
        return v


class GridSegment(BaseModel):
    length: float = Field(..., gt=0)
    bearing: float = Field(..., ge=-180, le=180)


class GridMission(BaseMission):

    camera: CameraSpec
    along_track_spacing: float = Field(..., gt=0, description="Spacing between images along track")
    cross_track_spacing: float = Field(..., gt=0, description="Spacing between passes")
    grid_segments: Optional[List[GridSegment]] = None
    num_lines: Optional[int] = Field(default=None, ge=1)

    # Legacy support
    fov: Optional[float] = None
    line_spacing: Optional[float] = None

    @model_validator(mode='before')
    @classmethod
    def validate_grid(cls, values):
        """Validate grid parameters and handle legacy fields."""
        if 'camera' not in values or values.get('camera') is None:
            fov = values.get('fov')
            if fov is not None:
                values['camera'] = CameraSpec(
                    fov_h=fov,
                    fov_v=fov,
                    front_overlap=values.get('front_overlap', 0.3),
                    side_overlap=values.get('side_overlap', 0.3)
                )

        # Handle legacy line_spacing
        if not values.get('cross_track_spacing') and values.get('line_spacing'):
            values['cross_track_spacing'] = values['line_spacing']

        # Ensure along_track_spacing exists
        if not values.get('along_track_spacing') and values.get('cross_track_spacing'):
            values['along_track_spacing'] = values['cross_track_spacing']

        return values


class OrbitMission(BaseMission):
    type: Literal["orbit", "circle", "poi"]
    radius: float = Field(..., gt=0, le=10000)
    poi_location: Optional[Waypoint] = None
    num_orbits: int = Field(default=1, ge=1, le=100)
    direction: Literal['clockwise', 'counterclockwise'] = 'clockwise'
    min_standoff_m: float = Field(default=10, ge=0)

    @field_validator('radius')
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
    terrain_data_source: Optional[str] = None
    terrain_profile: Optional[List[float]] = None

    @model_validator(mode='after')
    def validate_agl_range(self):
        """Ensure max_agl is strictly greater than min_agl."""
        if self.max_agl <= self.min_agl:
            raise ValueError(
                f"max_agl ({self.max_agl}) must be greater than min_agl ({self.min_agl})"
            )
        return self


class PerimeterPatrolMission(BaseMission):
    type: Literal["perimeter_patrol", "private_patrol", "polygon", "patrol"]
    polygon: List[Waypoint] = Field(..., min_length=3)
    path_offset_m: float = Field(default=0, ge=0)
    boundary_buffer_min: float = Field(default=10, ge=0)
    check_self_intersection: bool = True

    @field_validator('polygon')
    @classmethod
    def validate_polygon(cls, v):
        """Validate polygon has at least 3 points."""
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 points")
        return v


class AdaptiveAltitudeMission(BaseMission):
    type: Literal["adaptive_altitude"]
    target_agl: float = Field(..., gt=0, le=500)
    alt_ceiling_msl: float = Field(..., gt=0)
    alt_floor_msl: float = Field(..., ge=-500)
    agl_min: float = Field(default=5, ge=0)
    agl_max: float = Field(default=400, le=1000)


    @field_validator('alt_ceiling_msl')
    @classmethod
    def validate_ceiling(cls, v, info):
        """Ensure ceiling is above floor."""
        if 'alt_floor_msl' in info.data and v <= info.data['alt_floor_msl']:
            raise ValueError("Altitude ceiling must be above floor")
        return v


    @model_validator(mode='after')
    def validate_target_agl_within_envelope(self):
        """Ensure target_agl is within the agl_min/agl_max envelope."""
        if self.target_agl < self.agl_min:
            raise ValueError(
                f"target_agl ({self.target_agl}) is below agl_min ({self.agl_min})"
            )
        if self.target_agl > self.agl_max:
            raise ValueError(
                f"target_agl ({self.target_agl}) exceeds agl_max ({self.agl_max})"
            )
        return self

class PhotogrammetryMission(BaseMission):
    type: Literal["photogrammetry"]
    polygon: List[Waypoint] = Field(..., min_length=3)
    altitude_agl: float = Field(default=30.0, ge=10.0, le=120.0)
    front_overlap: float = Field(default=0.8, ge=0.5, le=0.95)
    side_overlap: float = Field(default=0.7, ge=0.5, le=0.95)
    min_spacing_m: float = Field(default=0.5, gt=0.0, le=10.0)
    camera_fov_h: float = Field(default=78.0, gt=0, lt=180)
    camera_fov_v: float = Field(default=62.0, gt=0, lt=180)
    max_flight_time_min: Optional[float] = None


Mission = Annotated[
    Union[
        WaypointMission,
        GridMission,
        PhotogrammetryMission,
        OrbitMission,
        TerrainFollowMission,
        PerimeterPatrolMission,
        AdaptiveAltitudeMission,
    ],
    Field(discriminator='type')
]


def create_mission_from_dict(data: dict) -> Mission:
    mission_type = data.get('type', '').lower()

    type_map = {
        'waypoint':          WaypointMission,
        'route':             WaypointMission,
        'grid':              GridMission,
        'survey':            GridMission,
        'photogrammetry':    PhotogrammetryMission,
        'orbit':             OrbitMission,
        'circle':            OrbitMission,
        'poi':               OrbitMission,
        'terrain_follow':    TerrainFollowMission,
        'perimeter_patrol':  PerimeterPatrolMission,
        'private_patrol':    PerimeterPatrolMission,
        'polygon':           PerimeterPatrolMission,
        'patrol':            PerimeterPatrolMission,
        'adaptive_altitude': AdaptiveAltitudeMission,
    }

    mission_class = type_map.get(mission_type)
    if mission_class is None:
        raise ValueError(f"Unknown mission type: {mission_type}")

    return mission_class(**data)
