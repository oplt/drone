from __future__ import annotations

from typing import Any

from backend.modules.warehouse.service.safety import evaluate_warehouse_runtime_safety


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _capabilities(components: dict[str, object]) -> dict[str, object]:
    raw = components.get("capabilities")
    return raw if isinstance(raw, dict) else {}


async def get_warehouse_mapping_runtime_status(mission_type: str | None) -> dict[str, Any] | None:
    if mission_type not in {"warehouse_scan", "indoor_exploration"}:
        return None
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    status = await build_warehouse_perception_port().status()
    components = status.components if isinstance(status.components, dict) else {}
    caps = _capabilities(components)
    safety = evaluate_warehouse_runtime_safety(components)
    return {
        "bridge_connected": status.reachable,
        "bridge_alive": _bool(caps.get("bridge_alive")) if caps else status.reachable,
        "ready": _bool(caps.get("can_fly_warehouse_scan"))
        if caps
        else status.ready,
        "status": status.status,
        "detail": status.detail,
        "profile": status.profile,
        "capabilities": caps,
        "health_layers": components.get("health_layers"),
        "can_fly_warehouse_scan": _bool(caps.get("can_fly_warehouse_scan")),
        "can_build_warehouse_map": _bool(caps.get("can_build_warehouse_map")),
        "ros_graph_ready": _bool(caps.get("ros_graph_ready", components.get("ros_graph"))),
        "vslam_tracking": _bool(
            components.get("slam_tracking_ok", components.get("visual_slam"))
        ),
        "nvblox_ready": _bool(components.get("nvblox")),
        "nvblox_fps": _number(components.get("nvblox_fps")),
        "mapped_volume_m3": _number(components.get("mapped_volume_m3")),
        "mapped_area_m2": _number(components.get("mapped_area_m2")),
        "dropped_frames": _number(components.get("dropped_frames")),
        "depth_healthy": _bool(components.get("depth_health", components.get("depth"))),
        "disk_free_gb": _number(components.get("disk_free_gb")),
        "localization_confidence": _number(components.get("localization_confidence")),
        "odometry_drift_m": _number(components.get("odometry_drift_m")),
        "frontier_count": _number(components.get("frontier_count")),
        "exploration_state": components.get("exploration_state"),
        "health_sample_timestamp": components.get("health_sample_timestamp"),
        "from_cache": components.get("from_cache"),
        "probe_mode": components.get("probe_mode"),
        "safety_action": safety.action,
        "safety_reason": safety.reason,
    }
