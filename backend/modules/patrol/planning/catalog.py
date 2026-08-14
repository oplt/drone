from __future__ import annotations

from typing import Any

from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS

_PRIVATE_PATROL_TASK_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "perimeter_patrol",
        "label": "Perimeter Patrol Mission",
        "purpose": "Continuous surveillance of property borders.",
        "description": (
            "Generate an offset perimeter route, patrol in the selected direction, "
            "and run AI detections for rapid anomaly verification."
        ),
        "default_params": {
            "altitude_m": 30.0,
            "speed_mps": 6.0,
            "path_offset_m": 15.0,
            "direction": "clockwise",
            "camera_angle_deg": 35.0,
            "camera_overlap_pct": 50.0,
            "patrol_loops": 1,
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
    {
        "id": "waypoint_patrol",
        "label": "Waypoint Patrol (Key Points)",
        "purpose": "Monitor specific sensitive areas instead of the full perimeter.",
        "description": (
            "Visit ordered security checkpoints such as gate, parking, storage, "
            "back fence, and roof. At each point: hover, run 360° scan, and capture zoom evidence."
        ),
        "default_params": {
            "altitude_m": 30.0,
            "speed_mps": 5.0,
            "hover_time_s": 15.0,
            "camera_scan_yaw_deg": 360.0,
            "zoom_capture": True,
            "return_to_start": True,
            "example_checkpoints": [
                "Gate",
                "Garage",
                "Back yard",
                "Parking lot",
                "Warehouse doors",
                "Roof",
            ],
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
    {
        "id": "grid_surveillance",
        "label": "Grid Surveillance Mission",
        "purpose": "Full area monitoring for large private properties.",
        "description": (
            "Generate a lawnmower coverage pattern for broad-area monitoring such as "
            "farms, solar parks, estates, and construction sites."
        ),
        "default_params": {
            "altitude_m": 28.0,
            "speed_mps": 5.0,
            "grid_spacing_m": 40.0,
            "grid_angle_deg": 0.0,
            "safety_inset_m": 2.0,
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
    {
        "id": "event_triggered_patrol",
        "label": "Event-Triggered Patrol",
        "purpose": "Rapid response and visual verification triggered by security events.",
        "description": (
            "On trigger events (fence breach, motion, unknown vehicle), launch, move to "
            "event location, verify/track target, and stream verification context to operators."
        ),
        "default_params": {
            "speed_mps": 6.0,
            "verification_loiter_s": 45.0,
            "track_target": True,
            "auto_stream_video": True,
            "verification_radius_m": 18.0,
            "search_grid_spacing_m": 40.0,
        },
        "ai_tasks": list(PATROL_AI_TASKS),
    },
)


def private_patrol_task_catalog() -> list[dict[str, Any]]:
    """List available private patrol mission templates/tasks."""
    return [dict(item) for item in _PRIVATE_PATROL_TASK_CATALOG]
