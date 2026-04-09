from __future__ import annotations

INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS = [
    "Heartbeat Age",
    "Message Rate",
    "Vehicle Armable",
    "Flight Mode",
    "Arming Checks",
    "Battery Voltage",
    "Indoor Estimator",
    "Indoor Local Position",
    "Indoor LiDAR",
    "Indoor Rangefinder",
    "Indoor SLAM Pipeline",
    "Indoor Dock Reference",
    "Indoor Takeoff Bubble",
]

INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS = [
    "Indoor Mission Parameters",
    "Indoor Frames",
    "Indoor Dock Geometry",
    "Indoor Return Reserve",
    "Indoor Localization Thresholds",
]


def indoor_warehouse_overrides() -> dict[str, object]:
    return {
        "ENFORCE_PREFLIGHT_RANGE": False,
        "HOME_POSITION_REQUIRED": False,
        "GPS_FIX_TYPE_MIN": 0,
        "SAT_MIN": 0,
        "HDOP_MAX": 99.0,
        "HEARTBEAT_MAX_AGE": 2.5,
        "INDOOR_PROXIMITY_REQUIRED": True,
        "INDOOR_PREFLIGHT_LOCALIZATION_MIN": 0.55,
    }
