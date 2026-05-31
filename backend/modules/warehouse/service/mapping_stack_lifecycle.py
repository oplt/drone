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
from backend.modules.warehouse.service.takeoff_readiness import readiness_from_perception_status

logger = logging.getLogger(__name__)

_DEFAULT_PREFLIGHT_WAIT_S = 20.0
_PREFLIGHT_POLL_S = 0.5


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
    def core_ready(self) -> bool:
        return bool(self.bridge_reachable and self.sensors_ready)

    @property
    def mapping_ready(self) -> bool:
        return bool(self.nvblox_ready)

    @property
    def ready_for_preflight(self) -> bool:
        if _preflight_wait_for_nvblox():
            return self.core_ready and self.nvblox_ready
        return self.core_ready

    def to_dict(self) -> dict[str, object]:
        return {
            "stack": self.stack_status.to_dict(),
            "bridge_reachable": self.bridge_reachable,
            "ros_graph_ready": self.ros_graph_ready,
            "sensors_ready": self.sensors_ready,
            "core_ready": self.core_ready,
            "nvblox_ready": self.nvblox_ready,
            "mapping_ready": self.mapping_ready,
            "ready_for_preflight": self.ready_for_preflight,
            "missing_required_topics": list(self.missing_required),
            "missing_nvblox_topics": list(self.missing_nvblox),
            "topic_diagnostics": self.topic_diagnostics,
            "detail": self.detail,
            "suggested_actions": list(self.suggested_actions),
        }


def _preflight_wait_for_nvblox() -> bool:
    raw = os.getenv("WAREHOUSE_PREFLIGHT_WAIT_NVBLOX", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _preflight_poll_interval_s() -> float:
    raw = os.getenv("WAREHOUSE_READINESS_POLL_S", "0.5")
    try:
        return max(0.25, float(raw))
    except ValueError:
        return 0.5


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
    diagnostics_ready = bool(components.get("diagnostics_ready", True))
    takeoff = readiness_from_perception_status(status, require_nvblox=False, strict=True)
    sensors_ready = bool(status.ready) if diagnostics_ready else False
    if diagnostics_ready:
        sensors_ready = takeoff.ready
    nvblox_ready = (
        bool(components.get("nvblox_healthy", components.get("nvblox")))
        if diagnostics_ready
        else False
    )
    topic_diagnostics = takeoff.topic_diagnostics
    detail = status.detail if diagnostics_ready else "waiting for warehouse bridge diagnostics"
    if diagnostics_ready and not sensors_ready and takeoff.detail:
        detail = takeoff.detail
    if takeoff.missing_topics or takeoff.stale_topics:
        missing_required = tuple(
            dict.fromkeys((*missing_required, *takeoff.missing_topics, *takeoff.stale_topics))
        )
    return WarehouseMappingReadiness(
        stack_status=stack_status,
        bridge_reachable=bool(status.reachable),
        ros_graph_ready=bool(components.get("ros_graph")),
        sensors_ready=sensors_ready,
        nvblox_ready=nvblox_ready,
        missing_required=missing_required,
        missing_nvblox=missing_nvblox,
        detail=detail,
        topic_diagnostics=topic_diagnostics,
        suggested_actions=_suggested_actions(
            bridge_reachable=bool(status.reachable),
            sensors_ready=sensors_ready,
            nvblox_ready=nvblox_ready,
            missing_required=missing_required,
            missing_nvblox=missing_nvblox,
            components=components,
        )
        or takeoff.suggested_actions,
    )


async def ensure_warehouse_mapping_stack_running() -> MappingStackStatus:
    manager = get_warehouse_mapping_stack_manager()
    return await asyncio.to_thread(manager.start)


async def ensure_warehouse_mapping_ready_for_preflight(
    *,
    timeout_s: float | None = None,
) -> WarehouseMappingReadiness:
    """Wait for bridge sensor readiness without starting nvblox (flight starts the stack)."""
    stack_status = await warehouse_mapping_stack_status()

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

    poll_s = _preflight_poll_interval_s()
    deep_interval_s = float(os.getenv("WAREHOUSE_READINESS_DEEP_INTERVAL_S", "6.0"))
    last_deep_at = 0.0
    attempt = 0

    while time.monotonic() < deadline:
        now = time.monotonic()
        attempt += 1
        use_deep = attempt == 1 or (now - last_deep_at) >= deep_interval_s
        if use_deep:
            last_deep_at = now

        status = await port.status(deep=use_deep, force=attempt == 1)
        last = _readiness_from_status(status, stack_status=stack_status)
        components = status.components if isinstance(status.components, dict) else {}
        diagnostics_ready = bool(components.get("diagnostics_ready", True))
        if not diagnostics_ready or (
            components.get("probe_in_progress") and not components.get("cache_ready")
        ):
            await asyncio.sleep(poll_s)
            continue
        if last.ready_for_preflight:
            logger.info(
                "Warehouse mapping ready for preflight sensors=%s nvblox=%s",
                last.sensors_ready,
                last.nvblox_ready,
            )
            return last
        await asyncio.sleep(poll_s)

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


async def prepare_warehouse_scan_ros(
    *,
    require_nvblox: bool = False,
    sensor_timeout_s: float | None = None,
    nvblox_timeout_s: float | None = None,
) -> tuple[MappingStackStatus, WarehouseMappingReadiness, "WarehouseTakeoffReadiness"]:
    """Start nvblox and confirm sensors in parallel with takeoff readiness (faster flight prep)."""
    from backend.modules.warehouse.service.takeoff_readiness import (
        WarehouseTakeoffReadiness,
        ensure_warehouse_takeoff_readiness,
    )

    stack_status = await ensure_warehouse_mapping_stack_running()
    if not stack_status.running:
        readiness = WarehouseMappingReadiness(
            stack_status=stack_status,
            bridge_reachable=False,
            sensors_ready=False,
            nvblox_ready=False,
            detail=stack_status.last_error or "mapping stack failed to start",
        )
        takeoff_ready = WarehouseTakeoffReadiness(
            ready=False,
            detail=readiness.detail,
        )
        return stack_status, readiness, takeoff_ready

    settle_s = float(os.getenv("WAREHOUSE_MAPPING_STACK_SETTLE_S", "2.0"))
    if settle_s > 0:
        await asyncio.sleep(settle_s)

    mapping_ready_task = asyncio.create_task(
        _wait_bridge_after_stack_start(
            stack_status=stack_status,
            timeout_s=nvblox_timeout_s,
            require_nvblox=require_nvblox,
        )
    )
    takeoff_ready_task = asyncio.create_task(
        ensure_warehouse_takeoff_readiness(
            timeout_s=sensor_timeout_s,
            require_nvblox=False,
            reuse_recent=False,
            strict=True,
            force_refresh=True,
        )
    )
    mapping_readiness, takeoff_ready = await asyncio.gather(
        mapping_ready_task,
        takeoff_ready_task,
    )
    return stack_status, mapping_readiness, takeoff_ready


async def _wait_bridge_after_stack_start(
    *,
    stack_status: MappingStackStatus,
    timeout_s: float | None,
    require_nvblox: bool,
) -> WarehouseMappingReadiness:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    wait_s = timeout_s if timeout_s is not None else float(
        os.getenv("WAREHOUSE_FLIGHT_MAPPING_WAIT_S", "30")
    )
    port = build_warehouse_perception_port()
    deadline = time.monotonic() + max(3.0, wait_s)
    last = WarehouseMappingReadiness(
        stack_status=stack_status,
        bridge_reachable=False,
        sensors_ready=False,
        nvblox_ready=False,
        detail="waiting for bridge after nvblox start",
    )
    poll_s = _preflight_poll_interval_s()
    deep_interval_s = float(os.getenv("WAREHOUSE_READINESS_DEEP_INTERVAL_S", "8.0"))
    last_deep_at = 0.0
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        now = time.monotonic()
        use_deep = (now - last_deep_at) >= deep_interval_s and attempt > 3
        if use_deep:
            last_deep_at = now

        status = await port.status(deep=use_deep, force=use_deep)
        last = _readiness_from_status(status, stack_status=stack_status)
        components = status.components if isinstance(status.components, dict) else {}
        if not status.reachable:
            await asyncio.sleep(poll_s)
            continue
        if components.get("probe_in_progress") and not components.get("cache_ready"):
            await asyncio.sleep(poll_s)
            continue
        if last.core_ready and (not require_nvblox or last.mapping_ready):
            logger.info(
                "Warehouse flight ROS ready sensors=%s nvblox=%s stack_pid=%s",
                last.sensors_ready,
                last.nvblox_ready,
                stack_status.pid,
            )
            return last
        await asyncio.sleep(poll_s)

    logger.warning(
        "Warehouse flight ROS wait timed out sensors=%s nvblox=%s",
        last.sensors_ready,
        last.nvblox_ready,
    )
    return last


async def ensure_warehouse_mapping_stack_for_flight(
    *,
    timeout_s: float | None = None,
    require_nvblox: bool = False,
) -> tuple[MappingStackStatus, WarehouseMappingReadiness]:
    """Start nvblox and wait for bridge/mapping readiness without repeating takeoff readiness."""
    stack_status = await ensure_warehouse_mapping_stack_running()
    if not stack_status.running:
        return stack_status, WarehouseMappingReadiness(
            stack_status=stack_status,
            bridge_reachable=False,
            sensors_ready=False,
            nvblox_ready=False,
            detail=stack_status.last_error or "mapping stack failed to start",
        )

    settle_s = float(os.getenv("WAREHOUSE_MAPPING_STACK_SETTLE_S", "2.0"))
    if settle_s > 0:
        await asyncio.sleep(settle_s)

    readiness = await _wait_bridge_after_stack_start(
        stack_status=stack_status,
        timeout_s=timeout_s,
        require_nvblox=require_nvblox,
    )
    return stack_status, readiness


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
