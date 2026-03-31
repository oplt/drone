from __future__ import annotations

from enum import Enum


class IndoorFrame(str, Enum):
    BODY = "body"
    ODOM = "odom"
    MAP = "map"
    DOCK = "dock"


class IndoorMissionState(str, Enum):
    IDLE_AT_DOCK = "IDLE_AT_DOCK"
    INDOOR_PREFLIGHT = "INDOOR_PREFLIGHT"
    TAKEOFF_SAFE_BUBBLE = "TAKEOFF_SAFE_BUBBLE"
    BOOTSTRAP_LOCAL_MAP = "BOOTSTRAP_LOCAL_MAP"
    BUILD_SKELETON = "BUILD_SKELETON"
    SELECT_FRONTIER = "SELECT_FRONTIER"
    TRANSIT_TO_FRONTIER = "TRANSIT_TO_FRONTIER"
    MAP_FRONTIER_REGION = "MAP_FRONTIER_REGION"
    FORCE_LOOP_CLOSURE = "FORCE_LOOP_CLOSURE"
    CHECK_RETURN_MARGIN = "CHECK_RETURN_MARGIN"
    RETURN_TO_DOCK = "RETURN_TO_DOCK"
    PRECISION_DOCK = "PRECISION_DOCK"
    LAND_AND_FINALIZE = "LAND_AND_FINALIZE"
    PAUSE_RELOCALIZE = "PAUSE_RELOCALIZE"
    BACKTRACK_TO_CONFIRMED_NODE = "BACKTRACK_TO_CONFIRMED_NODE"
    SAFE_LAND = "SAFE_LAND"
    ABORT_MISSION = "ABORT_MISSION"


class OccupancyState(str, Enum):
    UNKNOWN = "unknown"
    FREE = "free"
    OCCUPIED = "occupied"


class LocalizationConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOST = "lost"
