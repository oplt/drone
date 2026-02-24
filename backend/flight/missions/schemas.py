# drone/missions/schemas.py

from typing import List, Optional, Union, Literal, Annotated
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from enum import Enum
from math import tan, radians


class MissionType(str, Enum):
    GRID = "grid"
    ORBIT = "orbit"
    TERRAIN_FOLLOW = "terrain_follow"
    PERIMETER_PATROL = "perimeter_patrol"
    ADAPTIVE_ALTITUDE = "adaptive_altitude"
    SURVEY = "survey"       # alias for grid
    CIRCLE = "circle"       # alias for orbit
    POI = "poi"             # alias for orbit
    POLYGON = "polygon"     # alias for perimeter_patrol
    PATROL = "patrol"       # alias for perimeter_patrol


# ---------------------------------------------------------------------------
# Waypoint — defined BEFORE BaseMission so the forward-ref string is not needed
# ---------------------------------------------------------------------------

class Waypoint(BaseModel):
    """Waypoint model with validation."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: Optional[float] = None
    altitude_msl: Optional[float] = None
    target_agl: Optional[float] = None

    # BUG FIX 1: @root_validator → @model_validator(mode='before') for Pydantic v2.
    # In v2, @root_validator is removed; use @model_validator.
    # mode='before' gives us a plain dict so .get() works the same way as before.
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


# ---------------------------------------------------------------------------
# BaseMission
# ---------------------------------------------------------------------------

class BaseMission(BaseModel):
    """Base mission model with common fields."""
    # BUG FIX 2: class Config → model_config = ConfigDict(...) for Pydantic v2.
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    type: MissionType
    # BUG FIX 3: 'Waypoint' was a forward-reference string because Waypoint was
    # defined AFTER BaseMission in the original file. In Pydantic v2 unresolved
    # forward refs raise a PydanticUserError unless model_rebuild() is called
    # explicitly — which the original file never did. Moving Waypoint above
    # BaseMission lets us use the class directly and eliminates the issue.
    waypoints: List[Waypoint]
    speed: Optional[float] = Field(default=10.0, ge=0.1, le=50.0)
    altitude_agl: Optional[float] = Field(default=30.0, ge=5.0, le=500.0)


# ---------------------------------------------------------------------------
# CameraSpec
# ---------------------------------------------------------------------------

class CameraSpec(BaseModel):
    """Camera specifications for grid missions."""
    fov_h: float = Field(..., gt=0, lt=180, description="Horizontal field of view in degrees")
    fov_v: float = Field(..., gt=0, lt=180, description="Vertical field of view in degrees")
    front_overlap: float = Field(default=0.3, ge=0, le=1.0)
    side_overlap: float = Field(default=0.3, ge=0, le=1.0)

    # BUG FIX 4: @validator → @field_validator for Pydantic v2.
    # @validator is removed in v2. @field_validator requires @classmethod.
    # The second argument is now a FieldValidationInfo object (named 'info');
    # previously-validated sibling fields live in info.data, not in 'values'.
    @field_validator('fov_v')
    @classmethod
    def validate_fov(cls, v, info):
        """Ensure FOV is reasonable."""
        if 'fov_h' in info.data and v > info.data['fov_h'] * 2:
            raise ValueError("Vertical FOV unusually large compared to horizontal FOV")
        return v


# ---------------------------------------------------------------------------
# GridSegment — defined BEFORE GridMission so the forward-ref string is not needed
# ---------------------------------------------------------------------------

class GridSegment(BaseModel):
    """Individual grid segment."""
    length: float = Field(..., gt=0)
    bearing: float = Field(..., ge=-180, le=180)


# ---------------------------------------------------------------------------
# GridMission
# ---------------------------------------------------------------------------

class GridMission(BaseMission):
    """Grid/Survey mission with camera specifications."""
    # BUG FIX 5: Literal[MissionType.GRID, MissionType.SURVEY] breaks with
    # use_enum_values=True in Pydantic v2. When that setting is active the stored
    # field value is the raw string (e.g. "grid"), not the enum member. Literal
    # must therefore contain the raw string values, otherwise validation always
    # fails for this discriminated field. Same fix applied to every mission class.
    type: Literal["grid", "survey"]

    camera: CameraSpec
    along_track_spacing: float = Field(..., gt=0, description="Spacing between images along track")
    cross_track_spacing: float = Field(..., gt=0, description="Spacing between passes")

    # BUG FIX 6: 'GridSegment' was a forward-reference string because GridSegment
    # was defined AFTER GridMission in the original file. Same issue as Waypoint
    # above. Moving GridSegment before GridMission resolves it.
    grid_segments: Optional[List[GridSegment]] = None
    num_lines: Optional[int] = Field(default=None, ge=1)

    # Legacy support
    fov: Optional[float] = None
    line_spacing: Optional[float] = None

    # BUG FIX 7: @root_validator → @model_validator(mode='before') for Pydantic v2.
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


# ---------------------------------------------------------------------------
# OrbitMission
# ---------------------------------------------------------------------------

class OrbitMission(BaseMission):
    """Orbit/POI mission."""
    # BUG FIX 5 (same): raw string literals instead of enum members in Literal.
    type: Literal["orbit", "circle", "poi"]

    radius: float = Field(..., gt=0, le=10000)
    poi_location: Optional[Waypoint] = None
    num_orbits: int = Field(default=1, ge=1, le=100)
    direction: Literal['clockwise', 'counterclockwise'] = 'clockwise'
    min_standoff_m: float = Field(default=10, ge=0)

    # BUG FIX 4 (same): @validator → @field_validator with @classmethod.
    @field_validator('radius')
    @classmethod
    def validate_radius(cls, v):
        """Ensure radius is reasonable."""
        if v < 5:
            raise ValueError("Orbit radius too small (<5m)")
        return v


# ---------------------------------------------------------------------------
# TerrainFollowMission
# ---------------------------------------------------------------------------

class TerrainFollowMission(BaseMission):
    """Terrain-following mission."""
    # BUG FIX 5 (same): raw string literal.
    type: Literal["terrain_follow"]

    terrain_sample_step: float = Field(default=10, gt=0, le=500)
    min_agl: float = Field(default=10, ge=2)
    # BUG FIX 8: max_agl was missing a lower-bound (ge) constraint, and there was
    # no cross-field check that max_agl > min_agl. A caller could pass
    # max_agl=5, min_agl=10 and every individual field check would still pass,
    # producing an unsatisfiable mission. Added ge=2 and a model_validator.
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


# ---------------------------------------------------------------------------
# PerimeterPatrolMission
# ---------------------------------------------------------------------------

class PerimeterPatrolMission(BaseMission):
    """Perimeter patrol mission following a polygon."""
    # BUG FIX 5 (same): raw string literals.
    type: Literal["perimeter_patrol", "polygon", "patrol"]

    # BUG FIX 9: min_items is a Pydantic v1 Field keyword. In Pydantic v2 the
    # equivalent for sequences is min_length. Using the old keyword silently does
    # nothing in v2, so a 0- or 1-point polygon would bypass Field validation
    # entirely and only be caught by the field_validator below — which is fragile.
    polygon: List[Waypoint] = Field(..., min_length=3)
    path_offset_m: float = Field(default=0, ge=0)
    boundary_buffer_min: float = Field(default=10, ge=0)
    check_self_intersection: bool = True

    # BUG FIX 4 (same): @validator → @field_validator with @classmethod.
    @field_validator('polygon')
    @classmethod
    def validate_polygon(cls, v):
        """Validate polygon has at least 3 points."""
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 points")
        return v


# ---------------------------------------------------------------------------
# AdaptiveAltitudeMission
# ---------------------------------------------------------------------------

class AdaptiveAltitudeMission(BaseMission):
    """Adaptive altitude mission with terrain following."""
    # BUG FIX 5 (same): raw string literal.
    type: Literal["adaptive_altitude"]

    target_agl: float = Field(..., gt=0, le=500)
    alt_ceiling_msl: float = Field(..., gt=0)
    alt_floor_msl: float = Field(..., ge=-500)
    agl_min: float = Field(default=5, ge=0)
    agl_max: float = Field(default=400, le=1000)

    # BUG FIX 4 (same): @validator → @field_validator with @classmethod.
    # Critically, the original validator checked `if 'alt_floor_msl' in values`
    # where 'values' was the Pydantic v1 dict of previously-validated fields.
    # In v2, that dict is accessed via info.data — without this fix the
    # ceiling/floor cross-check silently never executes in v2.
    @field_validator('alt_ceiling_msl')
    @classmethod
    def validate_ceiling(cls, v, info):
        """Ensure ceiling is above floor."""
        if 'alt_floor_msl' in info.data and v <= info.data['alt_floor_msl']:
            raise ValueError("Altitude ceiling must be above floor")
        return v

    # BUG FIX 10: No validator ensures target_agl sits within [agl_min, agl_max].
    # A caller can pass target_agl=500 with agl_max=10 and all individual field
    # checks pass, creating a self-contradictory mission configuration.
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


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

# BUG FIX 11: The plain Union works in v2 but without a discriminator Pydantic
# tries each model in order and picks the first that validates. This can produce
# silent wrong-type matches. Using Annotated + Field(discriminator='type') makes
# selection exact and O(1), and raises a clear error for unknown type values.
Mission = Annotated[
    Union[
        GridMission,
        OrbitMission,
        TerrainFollowMission,
        PerimeterPatrolMission,
        AdaptiveAltitudeMission,
    ],
    Field(discriminator='type')
]


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def create_mission_from_dict(data: dict) -> Mission:
    """Create appropriate mission model from dictionary."""
    # BUG FIX 12: The original compared MissionType enum members against a plain
    # lowercase string (e.g. mission_type in [MissionType.GRID, MissionType.SURVEY]).
    # Even though MissionType is a str-Enum, `"grid" == MissionType.GRID` is True
    # in Python, BUT `"grid" in [MissionType.GRID]` is also True — so this was
    # accidentally working. However it is fragile and misleading; a dict-based
    # dispatch is cleaner, faster, and unambiguous.
    mission_type = data.get('type', '').lower()

    type_map = {
        'grid':              GridMission,
        'survey':            GridMission,
        'orbit':             OrbitMission,
        'circle':            OrbitMission,
        'poi':               OrbitMission,
        'terrain_follow':    TerrainFollowMission,
        'perimeter_patrol':  PerimeterPatrolMission,
        'polygon':           PerimeterPatrolMission,
        'patrol':            PerimeterPatrolMission,
        'adaptive_altitude': AdaptiveAltitudeMission,
    }

    mission_class = type_map.get(mission_type)
    if mission_class is None:
        raise ValueError(f"Unknown mission type: {mission_type}")

    return mission_class(**data)