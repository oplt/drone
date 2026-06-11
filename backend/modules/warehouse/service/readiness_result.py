from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.modules.warehouse.service.map_source_config import ODOM_PREFLIGHT_TOPICS


@dataclass(frozen=True)
class WarehouseReadinessResult:
    bridge_alive: bool
    ros_graph_ready: bool
    can_localize: bool
    nvblox_ready: bool
    core_ready: bool
    bridge_reachable: bool
    ready: bool
    detail: str | None = None
    missing_required_topics: list[str] = field(default_factory=list)
    missing_nvblox_topics: list[str] = field(default_factory=list)
    unhealthy_topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge_alive": self.bridge_alive,
            "ros_graph_ready": self.ros_graph_ready,
            "can_localize": self.can_localize,
            "nvblox_ready": self.nvblox_ready,
            "core_ready": self.core_ready,
            "bridge_reachable": self.bridge_reachable,
            "ready": self.ready,
            "detail": self.detail,
            "missing_required_topics": self.missing_required_topics,
            "missing_nvblox_topics": self.missing_nvblox_topics,
            "unhealthy_topics": self.unhealthy_topics,
        }


def readiness_from_perception_status_strict(status: Any) -> WarehouseReadinessResult:
    components = status.components if isinstance(getattr(status, "components", None), dict) else {}
    listed_topics = components.get("listed_topics")
    listed = {str(topic) for topic in listed_topics} if isinstance(listed_topics, list) else set()
    odom_topic = str(
        components.get("odometry_topic")
        or next(iter(ODOM_PREFLIGHT_TOPICS), "/warehouse/drone/odometry")
    )
    bridge_alive = bool(
        getattr(status, "reachable", False)
        or components.get("ros_graph_healthy")
        or components.get("preflight_core_ready")
        or listed
    )
    ros_graph_ready = bool(
        components.get("ros_graph_healthy")
        or components.get("ros_graph")
        or components.get("ros2_graph")
        or listed
        or bridge_alive
    )
    can_localize = bool(
        components.get("local_position_ok")
        or components.get("slam_ready")
        or components.get("slam_tracking_ok")
        or components.get("odometry_healthy")
        or components.get("preflight_core_ready")
        or odom_topic in listed
    )
    nvblox_ready = bool(
        components.get("nvblox_ok")
        or components.get("nvblox_ready")
        or components.get("nvblox_healthy")
        or any(
            topic == "/nvblox_node/static_esdf_pointcloud"
            or topic.startswith("nvblox_esdf_")
            or topic.startswith("/nvblox_esdf_")
            for topic in listed
        )
    )
    core_ready = bool(
        components.get("preflight_core_ready")
        or (bridge_alive and can_localize)
    )
    return WarehouseReadinessResult(
        bridge_alive=bridge_alive,
        ros_graph_ready=ros_graph_ready,
        can_localize=can_localize,
        nvblox_ready=nvblox_ready,
        core_ready=core_ready,
        bridge_reachable=bridge_alive,
        ready=core_ready and nvblox_ready,
        detail=getattr(status, "detail", None),
        missing_required_topics=[] if can_localize else [odom_topic],
        missing_nvblox_topics=[] if nvblox_ready else ["/nvblox_node/static_esdf_pointcloud"],
    )


def readiness_for_takeoff(status: Any) -> WarehouseReadinessResult:
    """Sensor readiness for arm/takeoff — core bridge topics only, not nvblox."""
    base = readiness_from_perception_status_strict(status)
    ready = bool(base.core_ready and base.can_localize)
    detail = base.detail
    if not ready and not detail:
        detail = "Warehouse core sensor topics are not ready for takeoff."
    return WarehouseReadinessResult(
        **{
            **base.to_dict(),
            "ready": ready,
            "detail": detail,
        }
    )
