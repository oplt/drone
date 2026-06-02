from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.readiness_cache import (
    record_sensor_readiness,
    sensor_readiness_recent,
)
from backend.modules.warehouse.service.runtime_safety import (
    odometry_state_is_fresh,
    read_odometry_state_file,
)

_TAKEOFF_TOPIC_KEYS: tuple[str, ...] = (
    "rgb_image",
    "depth",
    "raw_lidar",
    "imu",
    "visual_slam_odom",
    "local_odometry",
)


def _read_live_odometry_state() -> dict[str, Any] | None:
    read = read_odometry_state_file()
    if read.unreadable:
        return None
    return read.payload


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def takeoff_requires_nvblox() -> bool:
    return _bool_env("WAREHOUSE_TAKEOFF_REQUIRE_NVBLOX", False)


@dataclass(frozen=True)
class WarehouseTakeoffReadiness:
    ready: bool
    missing_topics: tuple[str, ...] = ()
    stale_topics: tuple[str, ...] = ()
    odometry_fresh: bool = False
    nvblox_ready: bool = False
    bridge_reachable: bool = False
    detail: str | None = None
    suggested_actions: tuple[str, ...] = field(default_factory=tuple)
    topic_diagnostics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "missing_topics": list(self.missing_topics),
            "stale_topics": list(self.stale_topics),
            "odometry_fresh": self.odometry_fresh,
            "nvblox_ready": self.nvblox_ready,
            "bridge_reachable": self.bridge_reachable,
            "detail": self.detail,
            "suggested_actions": list(self.suggested_actions),
            "topic_diagnostics": self.topic_diagnostics,
        }


def _topic_diag_entry(
    topic_diagnostics: dict[str, object],
    key: str,
) -> dict[str, Any] | None:
    raw = topic_diagnostics.get(key)
    return raw if isinstance(raw, dict) else None


def _gazebo_sim_enabled() -> bool:
    return os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _takeoff_topic_keys() -> tuple[str, ...]:
    keys = list(_TAKEOFF_TOPIC_KEYS)
    require_lidar = os.getenv("WAREHOUSE_TAKEOFF_REQUIRE_RAW_LIDAR", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if _gazebo_sim_enabled() and not require_lidar:
        keys = [key for key in keys if key != "raw_lidar"]
    if _gazebo_sim_enabled() and os.getenv("WAREHOUSE_REQUIRE_LOCAL_ODOMETRY", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        keys = [key for key in keys if key != "local_odometry"]
    return tuple(keys)


def _topic_is_live(diag: dict[str, Any] | None, *, strict: bool = False) -> bool:
    if diag is None:
        return False
    if strict:
        from backend.modules.warehouse.service.readiness_result import topic_is_strictly_live

        return topic_is_strictly_live(diag)
    if diag.get("healthy"):
        return True
    state = diag.get("readiness_state")
    if state in {"ok_graph_presence", "shallow_present"}:
        return bool(diag.get("listed", True))
    if state in {"ok", "ok_via_messages"}:
        return bool(diag.get("publishing") or diag.get("publisher_count", 0) > 0)
    return bool(diag.get("publishing"))


def _odometry_is_live(
    components: dict[str, object],
    topic_diagnostics: dict[str, object],
    *,
    max_age_s: float,
    strict: bool = False,
) -> bool:
    if components.get("odometry_state_unreadable"):
        return False
    odom_state_raw = components.get("local_odometry_state")
    odom_state = odom_state_raw if isinstance(odom_state_raw, dict) else {}
    if odometry_state_is_fresh(odom_state, max_age_s=max_age_s):
        return True

    for key in ("visual_slam_odom", "local_odometry"):
        diag = _topic_diag_entry(topic_diagnostics, key)
        if _topic_is_live(diag, strict=True):
            return True

    if bool(components.get("odometry_fresh")) and not components.get("odometry_state_unreadable"):
        return True
    return False


def readiness_from_perception_status(
    status: WarehousePerceptionStatus,
    *,
    require_nvblox: bool | None = None,
    strict: bool = False,
) -> WarehouseTakeoffReadiness:
    require_nvblox = (
        takeoff_requires_nvblox() if require_nvblox is None else require_nvblox
    )
    components = status.components if isinstance(status.components, dict) else {}
    topic_diagnostics_raw = components.get("topic_diagnostics")
    topic_diagnostics = (
        topic_diagnostics_raw if isinstance(topic_diagnostics_raw, dict) else {}
    )

    missing: list[str] = []
    stale: list[str] = []
    for key in _takeoff_topic_keys():
        diag = _topic_diag_entry(topic_diagnostics, key)
        if not _topic_is_live(diag, strict=strict):
            if diag is None or diag.get("readiness_state") == "topic_missing":
                missing.append(key)
            else:
                stale.append(key)

    odom_max_age_s = _float_env("WAREHOUSE_TAKEOFF_ODOMETRY_MAX_AGE_S", 2.0)
    odom_fresh = _odometry_is_live(
        components,
        topic_diagnostics,
        max_age_s=odom_max_age_s,
        strict=strict,
    )

    nvblox_ready = bool(components.get("nvblox_healthy", components.get("nvblox")))
    nvblox_warming = bool(components.get("nvblox_warming_up"))
    nvblox_ok = nvblox_ready or (nvblox_warming and not require_nvblox)
    bridge_reachable = bool(status.reachable)

    ready = (
        bridge_reachable
        and not missing
        and not stale
        and odom_fresh
        and (nvblox_ok if require_nvblox else True)
    )

    detail_parts: list[str] = []
    if missing:
        detail_parts.append(f"missing topics: {', '.join(missing)}")
    if stale:
        detail_parts.append(f"stale topics: {', '.join(stale)}")
    if not odom_fresh:
        detail_parts.append(
            "warehouse odometry is stale or unavailable "
            f"(check: ros2 topic hz {os.getenv('WAREHOUSE_ODOMETRY_TOPIC', '/warehouse/drone/odometry')})"
        )
    if require_nvblox and not nvblox_ready:
        detail_parts.append("nvblox outputs not ready")

    suggested: list[str] = []
    if not bridge_reachable:
        suggested.append("Ensure warehouse_bridge is running on WAREHOUSE_ROS_BRIDGE_URL")
    if missing or stale or not odom_fresh:
        suggested.append(
            "Press Play in Gazebo (gz sim -r world.sdf) and wait for sensor topics to publish"
        )
        suggested.append(
            "Run: ros2 topic hz /warehouse/drone/odometry /warehouse/front/rgbd/image /imu"
        )
    if require_nvblox and not nvblox_ready:
        suggested.append("Wait for nvblox mesh/pointcloud topics after mapping stack starts")

    result = WarehouseTakeoffReadiness(
        ready=ready,
        missing_topics=tuple(missing),
        stale_topics=tuple(stale),
        odometry_fresh=odom_fresh,
        nvblox_ready=nvblox_ready,
        bridge_reachable=bridge_reachable,
        detail="; ".join(detail_parts) if detail_parts else None,
        suggested_actions=tuple(suggested),
        topic_diagnostics=topic_diagnostics,
    )
    if ready:
        record_sensor_readiness(ready=True, payload=result.to_dict())
    return result


async def ensure_warehouse_takeoff_readiness(
    *,
    timeout_s: float | None = None,
    require_nvblox: bool | None = None,
    reuse_recent: bool = True,
    strict: bool = True,
    force_refresh: bool = False,
) -> WarehouseTakeoffReadiness:
    import asyncio
    import time

    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    require_nvblox = (
        takeoff_requires_nvblox() if require_nvblox is None else require_nvblox
    )
    if reuse_recent and not force_refresh and not strict and sensor_readiness_recent(max_age_s=45.0):
        from backend.modules.warehouse.service.readiness_cache import (
            sensor_readiness_payload,
        )

        payload = sensor_readiness_payload()
        if payload:
            odom_max_age_s = _float_env("WAREHOUSE_TAKEOFF_ODOMETRY_MAX_AGE_S", 2.0)
            odom_state = _read_live_odometry_state()
            odom_fresh = odometry_state_is_fresh(odom_state, max_age_s=odom_max_age_s)
            cached_nvblox_ready = bool(payload.get("nvblox_ready", False))
            cached_bridge_reachable = bool(payload.get("bridge_reachable", True))
            if odom_fresh and cached_bridge_reachable and (cached_nvblox_ready or not require_nvblox):
                return WarehouseTakeoffReadiness(
                    ready=True,
                    odometry_fresh=True,
                    nvblox_ready=cached_nvblox_ready,
                    bridge_reachable=cached_bridge_reachable,
                    detail="reused recent sensor readiness",
                    topic_diagnostics=(
                        payload.get("topic_diagnostics")
                        if isinstance(payload.get("topic_diagnostics"), dict)
                        else {}
                    ),
                )

    wait_s = timeout_s if timeout_s is not None else _float_env(
        "WAREHOUSE_TAKEOFF_READINESS_WAIT_S", 12.0
    )
    poll_s = _float_env("WAREHOUSE_READINESS_POLL_S", 0.5)
    port = build_warehouse_perception_port()
    deadline = time.monotonic() + max(1.0, wait_s)
    last = WarehouseTakeoffReadiness(
        ready=False,
        detail="waiting for takeoff sensor readiness",
    )
    deep_interval_s = _float_env("WAREHOUSE_READINESS_DEEP_INTERVAL_S", 8.0)
    takeoff_deep = force_refresh or strict or os.getenv(
        "WAREHOUSE_TAKEOFF_DEEP_PROBE", "0"
    ).strip().lower() in {"1", "true", "yes", "on"}
    last_deep_at = 0.0
    attempt = 0

    while time.monotonic() < deadline:
        now = time.monotonic()
        attempt += 1
        use_deep = takeoff_deep and (
            force_refresh or attempt == 1 or (now - last_deep_at) >= deep_interval_s
        )
        if use_deep:
            last_deep_at = now

        status = await port.status(
            deep=use_deep,
            force=force_refresh or (use_deep and attempt == 1),
        )
        components = status.components if isinstance(status.components, dict) else {}
        if components.get("probe_in_progress") and not components.get("cache_ready"):
            await asyncio.sleep(poll_s)
            continue
        last = readiness_from_perception_status(
            status,
            require_nvblox=require_nvblox,
            strict=strict,
        )
        if last.ready:
            return last
        await asyncio.sleep(poll_s)

    return last
