from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from backend.infrastructure.warehouse.mapping_stack_process import (
    MappingStackStatus,
    get_warehouse_mapping_stack_manager,
)
from backend.modules.warehouse.ports import WarehousePerceptionCommandResult, WarehousePerceptionStatus

logger = logging.getLogger(__name__)

_DEFAULT_PREFLIGHT_WAIT_S = 60.0
_PREFLIGHT_POLL_S = 1.0


@dataclass(frozen=True)
class WarehouseMappingReadiness:
    stack_status: MappingStackStatus
    bridge_reachable: bool
    sensors_ready: bool
    nvblox_ready: bool
    missing_required: tuple[str, ...] = ()
    missing_nvblox: tuple[str, ...] = ()
    detail: str | None = None
    suggested_actions: tuple[str, ...] = field(default_factory=tuple)
    ros_graph_ready: bool = False
    topic_diagnostics: dict[str, object] = field(default_factory=dict)

    @property
    def ready_for_preflight(self) -> bool:
        return (
            self.stack_status.running
            and self.bridge_reachable
            and self.sensors_ready
            and self.nvblox_ready
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "stack": self.stack_status.to_dict(),
            "bridge_reachable": self.bridge_reachable,
            "ros_graph_ready": self.ros_graph_ready,
            "sensors_ready": self.sensors_ready,
            "nvblox_ready": self.nvblox_ready,
            "ready_for_preflight": self.ready_for_preflight,
            "missing_required_topics": list(self.missing_required),
            "missing_nvblox_topics": list(self.missing_nvblox),
            "topic_diagnostics": self.topic_diagnostics,
            "detail": self.detail,
            "suggested_actions": list(self.suggested_actions),
        }


def _preflight_wait_for_nvblox_only() -> bool:
    raw = os.getenv("WAREHOUSE_PREFLIGHT_WAIT_NVBLOX_ONLY", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _diagnostic_verify_actions(components: dict[str, object]) -> tuple[str, ...]:
    raw = components.get("topic_diagnostics")
    if not isinstance(raw, dict):
        return ()
    actions: list[str] = []
    for key, payload in raw.items():
        if not isinstance(payload, dict) or payload.get("healthy"):
            continue
        topic = payload.get("matched") or payload.get("expected")
        if not isinstance(topic, str) or not topic.strip():
            continue
        error = payload.get("error") or payload.get("readiness_state") or "unhealthy"
        actions.append(
            f"{key} ({error}): ros2 topic info {topic} && timeout 5 ros2 topic hz {topic}"
        )
    return tuple(actions)


def _suggested_actions(
    *,
    bridge_reachable: bool,
    sensors_ready: bool,
    nvblox_ready: bool,
    missing_required: tuple[str, ...],
    missing_nvblox: tuple[str, ...],
    components: dict[str, object] | None = None,
) -> tuple[str, ...]:
    actions: list[str] = []
    if not bridge_reachable:
        actions.append("Ensure warehouse_bridge is running on WAREHOUSE_ROS_BRIDGE_URL")
    if components is not None and not components.get("ros_graph"):
        actions.append(
            "ROS graph empty — check ROS_DOMAIN_ID and that gazebo_sensor_bridge is running"
        )
    if not sensors_ready:
        actions.append(
            "Start external Gazebo (e.g. gz sim -v4 -r your_world.sdf) and ensure sensor topics publish"
        )
        actions.append(
            "Run scripts/check_warehouse_ros_health.sh to verify bridged sensor topics"
        )
        actions.append(
            "Verify ros2 topic hz /warehouse/front/rgbd/image and /warehouse/drone/odometry"
        )
    if missing_required:
        actions.append(f"Restore required sensor topics: {', '.join(missing_required)}")
    if not nvblox_ready:
        actions.append("Start mapping stack / nvblox after sensors are live")
        if missing_nvblox:
            actions.append(f"Missing nvblox outputs: {', '.join(missing_nvblox)}")
    if components:
        actions.extend(_diagnostic_verify_actions(components))
    return tuple(dict.fromkeys(actions))


def _readiness_from_status(status: WarehousePerceptionStatus, *, stack_status: MappingStackStatus) -> WarehouseMappingReadiness:
    components = status.components if isinstance(status.components, dict) else {}
    missing_required = tuple(
        str(item) for item in (components.get("missing_required_topics") or []) if item
    )
    missing_nvblox = tuple(
        str(item) for item in (components.get("missing_nvblox_topics") or []) if item
    )
    sensors_ready = bool(status.ready)
    nvblox_ready = bool(components.get("nvblox_healthy", components.get("nvblox")))
    topic_diagnostics_raw = components.get("topic_diagnostics")
    topic_diagnostics = topic_diagnostics_raw if isinstance(topic_diagnostics_raw, dict) else {}
    return WarehouseMappingReadiness(
        stack_status=stack_status,
        bridge_reachable=bool(status.reachable),
        ros_graph_ready=bool(components.get("ros_graph")),
        sensors_ready=sensors_ready,
        nvblox_ready=nvblox_ready,
        missing_required=missing_required,
        missing_nvblox=missing_nvblox,
        detail=status.detail,
        topic_diagnostics=topic_diagnostics,
        suggested_actions=_suggested_actions(
            bridge_reachable=bool(status.reachable),
            sensors_ready=sensors_ready,
            nvblox_ready=nvblox_ready,
            missing_required=missing_required,
            missing_nvblox=missing_nvblox,
            components=components,
        ),
    )


async def ensure_warehouse_mapping_stack_running() -> MappingStackStatus:
    manager = get_warehouse_mapping_stack_manager()
    return await asyncio.to_thread(manager.start)


async def ensure_warehouse_mapping_ready_for_preflight(
    *,
    timeout_s: float | None = None,
) -> WarehouseMappingReadiness:
    """Start mapping stack and wait until bridge reports sensor + nvblox readiness."""
    stack_status = await ensure_warehouse_mapping_stack_running()
    if not stack_status.running:
        return WarehouseMappingReadiness(
            stack_status=stack_status,
            bridge_reachable=False,
            sensors_ready=False,
            nvblox_ready=False,
            detail=stack_status.last_error or "mapping stack failed to start",
            suggested_actions=(
                "Inspect backend/storage/warehouse_ros/logs/warehouse_mapping_stack.log",
                "Set WAREHOUSE_NVBLOX_LAUNCH_CMD to scripts/start_warehouse_nvblox.sh",
            ),
        )

    wait_s = timeout_s if timeout_s is not None else float(
        os.getenv("WAREHOUSE_PREFLIGHT_PERCEPTION_WAIT_S", str(_DEFAULT_PREFLIGHT_WAIT_S))
    )
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    port = build_warehouse_perception_port()
    deadline = time.monotonic() + max(1.0, wait_s)
    last = WarehouseMappingReadiness(
        stack_status=stack_status,
        bridge_reachable=False,
        sensors_ready=False,
        nvblox_ready=False,
        detail="waiting for mapping readiness",
    )

    while time.monotonic() < deadline:
        status = await port.status(deep=True)
        last = _readiness_from_status(status, stack_status=stack_status)
        if _preflight_wait_for_nvblox_only():
            ready_for_preflight = last.nvblox_ready and last.sensors_ready
        else:
            ready_for_preflight = last.ready_for_preflight
        if ready_for_preflight:
            logger.info(
                "Warehouse mapping ready for preflight sensors=%s nvblox=%s",
                last.sensors_ready,
                last.nvblox_ready,
            )
            return last
        await asyncio.sleep(_PREFLIGHT_POLL_S)

    logger.warning(
        "Warehouse mapping stack not ready before preflight sensors=%s nvblox=%s timeout_s=%.0f missing_required=%s missing_nvblox=%s",
        last.sensors_ready,
        last.nvblox_ready,
        wait_s,
        list(last.missing_required),
        list(last.missing_nvblox),
    )
    return WarehouseMappingReadiness(
        stack_status=stack_status,
        bridge_reachable=last.bridge_reachable,
        sensors_ready=last.sensors_ready,
        nvblox_ready=last.nvblox_ready,
        missing_required=last.missing_required,
        missing_nvblox=last.missing_nvblox,
        detail=last.detail or "mapping stack readiness timed out",
        suggested_actions=last.suggested_actions
        or ("Increase WAREHOUSE_PREFLIGHT_PERCEPTION_WAIT_S",),
    )


async def shutdown_warehouse_mapping_stack() -> MappingStackStatus:
    manager = get_warehouse_mapping_stack_manager()
    return await asyncio.to_thread(manager.stop)


async def warehouse_mapping_stack_status() -> MappingStackStatus:
    manager = get_warehouse_mapping_stack_manager()
    return await asyncio.to_thread(manager.status)


def mapping_stack_not_running_result() -> WarehousePerceptionCommandResult:
    return WarehousePerceptionCommandResult(
        accepted=False,
        status="mapping_stack_unavailable",
        detail="Warehouse ROS mapping stack is not running",
    )
