from __future__ import annotations

WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS = [
    "Warehouse ROS Position",
    "Warehouse ROS Odometry",
]

WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS = [
    "Warehouse ROS Bridge",
    "Warehouse ROS Graph",
    "Warehouse Camera Topics",
    "Warehouse IMU Topic",
    "Warehouse Visual SLAM",
    "Warehouse Local Position",
]

# Non-blocking for mission start (WARN still allows start when ALLOW_WARN_PREFLIGHT_START=1).
WAREHOUSE_SCAN_OPTIONAL_MISSION_CHECKS = [
    "Warehouse Nvblox",
    "Warehouse Stereo Sync",
    "Warehouse TF Tree",
    "Warehouse Mapping Disk",
    "Warehouse Sensor Rig",
    "Warehouse Battery Margin",
    "Warehouse Dock Marker",
]


def warehouse_scan_preflight_overrides() -> dict[str, object]:
    return {
        "ENFORCE_PREFLIGHT_RANGE": False,
        "HOME_POSITION_REQUIRED": False,
        "GPS_FIX_TYPE_MIN": 0,
        "SAT_MIN": 0,
        "HDOP_MAX": 99.0,
        "HEARTBEAT_MAX_AGE": 99.0,
        "MSG_RATE_MIN_HZ": 0.0,
        "WAREHOUSE_ODOMETRY_DRIFT_MAX_M": 0.75,
        "WAREHOUSE_MAPPING_DISK_FREE_GB_MIN": 1.0,
        "WAREHOUSE_SCAN_BATTERY_RESERVE_PCT": 0.0,
    }
