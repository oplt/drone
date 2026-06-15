from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from backend.modules.warehouse.service.map_source_config import (
    NVBLOX_OPTIONAL_ESDF_TOPICS,
    NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
    ODOM_PREFLIGHT_TOPICS,
)

_TRUE_VALUES = {"1", "true", "yes", "y", "on", "ok", "ready", "healthy", "live"}
_FALSE_VALUES = {"0", "false", "no", "n", "off", "none", "null", "blocked", "unhealthy", "error"}


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
            "missing_required_topics": list(self.missing_required_topics),
            "missing_nvblox_topics": list(self.missing_nvblox_topics),
            "unhealthy_topics": list(self.unhealthy_topics),
        }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(text)


def _explicit_false(value: Any) -> bool:
    if value is False:
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, str) and value.strip().lower() in _FALSE_VALUES:
        return True
    return False


def _as_topic_set(value: Any) -> set[str]:
    if isinstance(value, (set, list, tuple, frozenset)):
        return {str(topic).strip() for topic in value if str(topic).strip()}
    return set()


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, (set, list, tuple, frozenset)):
        return sorted({str(item).strip() for item in value if str(item).strip()})
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _detail_from_status(status: Any) -> str | None:
    value = getattr(status, "detail", None)
    if value is None:
        return None
    text = str(value).strip()
    return text[:500] if text else None


def _nvblox_topic_ready(topic: str) -> bool:
    if topic in NVBLOX_REQUIRED_POINTCLOUD_TOPICS or topic in NVBLOX_OPTIONAL_ESDF_TOPICS:
        return True
    if topic.startswith("/nvblox_node/") and topic.endswith("_esdf_pointcloud"):
        return True
    if topic.startswith("nvblox_esdf_") or topic.startswith("/nvblox_esdf_"):
        return True
    return False


def _first_topic(topics: Iterable[str], fallback: str) -> str:
    for topic in topics:
        token = str(topic).strip()
        if token:
            return token
    return fallback


def readiness_from_perception_status_strict(status: Any) -> WarehouseReadinessResult:
    components = status.components if isinstance(getattr(status, "components", None), dict) else {}
    listed = _as_topic_set(components.get("listed_topics"))
    unhealthy_topics = _as_string_list(components.get("unhealthy_topics"))
    odom_topic = str(
        components.get("odometry_topic")
        or _first_topic(ODOM_PREFLIGHT_TOPICS, "/warehouse/drone/odometry")
    ).strip()

    bridge_alive = bool(
        _truthy(getattr(status, "reachable", False))
        or _truthy(components.get("bridge_alive"))
        or _truthy(components.get("ros_graph_healthy"))
        or _truthy(components.get("preflight_core_ready"))
        or bool(listed)
    )
    if _explicit_false(components.get("bridge_alive")) or _explicit_false(getattr(status, "reachable", None)):
        bridge_alive = False

    ros_graph_ready = bool(
        _truthy(components.get("ros_graph_healthy"))
        or _truthy(components.get("ros_graph"))
        or _truthy(components.get("ros2_graph"))
        or bool(listed)
        or bridge_alive
    )
    if _explicit_false(components.get("ros_graph_healthy")):
        ros_graph_ready = False

    localization_negative = any(
        _explicit_false(components.get(key))
        for key in (
            "local_position_ok",
            "slam_ready",
            "slam_tracking_ok",
            "odometry_healthy",
        )
    )
    localization_positive = any(
        _truthy(components.get(key))
        for key in (
            "local_position_ok",
            "slam_ready",
            "slam_tracking_ok",
            "odometry_healthy",
            "preflight_core_ready",
        )
    )
    can_localize = bool(not localization_negative and (localization_positive or odom_topic in listed))

    nvblox_status = str(components.get("nvblox_status") or "").strip().lower()
    nvblox_negative = any(
        _explicit_false(components.get(key))
        for key in ("nvblox_ok", "nvblox_ready", "nvblox_healthy")
    ) or nvblox_status in {"off", "error"}
    nvblox_positive = any(
        _truthy(components.get(key))
        for key in ("nvblox_ok", "nvblox_ready", "nvblox_healthy")
    ) or nvblox_status in {"live", "ready", "warming", "degraded"}
    nvblox_ready = bool(
        not nvblox_negative
        and (
            nvblox_positive
            or any(_nvblox_topic_ready(topic) for topic in listed)
        )
    )

    core_ready = bool(
        _truthy(components.get("preflight_core_ready"))
        or (bridge_alive and ros_graph_ready and can_localize)
    )
    if _explicit_false(components.get("preflight_core_ready")) and not (bridge_alive and can_localize):
        core_ready = False

    missing_required_topics = [] if can_localize else [odom_topic]
    missing_nvblox_topics = [] if nvblox_ready else list(NVBLOX_REQUIRED_POINTCLOUD_TOPICS)

    return WarehouseReadinessResult(
        bridge_alive=bridge_alive,
        ros_graph_ready=ros_graph_ready,
        can_localize=can_localize,
        nvblox_ready=nvblox_ready,
        core_ready=core_ready,
        bridge_reachable=bridge_alive,
        ready=core_ready and nvblox_ready,
        detail=_detail_from_status(status),
        missing_required_topics=missing_required_topics,
        missing_nvblox_topics=missing_nvblox_topics,
        unhealthy_topics=unhealthy_topics,
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
