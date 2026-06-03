from __future__ import annotations

import asyncio
import logging
import os
import time

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.readiness_cache import (
    clear_sensor_readiness,
    record_sensor_readiness,
    sensor_readiness_payload,
    sensor_readiness_recent,
)
from backend.modules.warehouse.service.readiness_result import (
    WarehouseReadinessResult,
    readiness_from_perception_status_strict,
)

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _health_sample_age_ms(components: dict[str, object]) -> int | None:
    raw = components.get("health_sample_timestamp")
    if not isinstance(raw, (int, float)):
        return None
    return max(0, int((time.time() - float(raw)) * 1000.0))


def _preflight_sample_usable(
    result: WarehouseReadinessResult,
    components: dict[str, object],
) -> bool:
    if not result.can_fly_warehouse_scan:
        return False
    if not result.from_cache:
        return True
    if not components.get("cache_ready", True):
        return False
    if components.get("probe_in_progress"):
        return False
    age_ms = _health_sample_age_ms(components)
    max_age_ms = int(
        components.get("health_sample_max_age_ms")
        or components.get("health_cache_ttl_ms")
        or 90_000
    )
    if age_ms is not None and age_ms > max_age_ms:
        return False
    return True


def _result_from_recent_go_preflight() -> WarehouseReadinessResult | None:
    if not sensor_readiness_recent(
        max_age_s=_float_env("WAREHOUSE_SCAN_REUSE_READY_S", 180.0)
    ):
        return None
    payload = sensor_readiness_payload()
    if not isinstance(payload, dict) or not payload.get("can_fly_warehouse_scan"):
        return None
    return WarehouseReadinessResult(
        bridge_alive=bool(payload.get("bridge_alive")),
        ros_graph_ready=bool(payload.get("ros_graph_ready")),
        can_localize=bool(payload.get("can_localize")),
        can_perceive_depth=bool(payload.get("can_perceive_depth")),
        can_perceive_rgb=bool(payload.get("can_perceive_rgb")),
        can_scan_lidar=bool(payload.get("can_scan_lidar")),
        can_build_map=bool(payload.get("can_build_map", payload.get("can_build_warehouse_map"))),
        can_avoid_obstacles=bool(payload.get("can_avoid_obstacles")),
        can_fly_warehouse_scan=True,
        missing_required_topics=tuple(payload.get("missing_required_topics") or ()),
        unhealthy_topics=tuple(payload.get("unhealthy_topics") or ()),
        missing_nvblox_topics=tuple(payload.get("missing_nvblox_topics") or ()),
        failure_code=None,
        user_message=None,
        developer_message="reused recent warehouse go-preflight readiness",
        from_cache=True,
        probe_mode="go_preflight_reuse",
    )


async def _fetch_status(
    port: object,
    *,
    deep: bool,
    force: bool,
) -> WarehousePerceptionStatus:
    return await port.status(deep=deep, force=force)  # type: ignore[attr-defined]


async def ensure_warehouse_scan_preflight(
    *,
    timeout_s: float | None = None,
    require_nvblox_for_map: bool = False,
) -> WarehouseReadinessResult:
    """Confirm warehouse sensors before scan start without overloading ROS discovery."""
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    reused = _result_from_recent_go_preflight()
    if reused is not None:
        logger.info(
            "Warehouse scan preflight reusing recent go-preflight readiness age_s<=%.0f",
            _float_env("WAREHOUSE_SCAN_REUSE_READY_S", 180.0),
        )
        port = build_warehouse_perception_port()
        status = await _fetch_status(port, deep=False, force=False)
        if status.reachable:
            quick = readiness_from_perception_status_strict(
                status,
                require_nvblox_for_map=require_nvblox_for_map,
            )
            components = status.components if isinstance(status.components, dict) else {}
            if _preflight_sample_usable(quick, components):
                return quick
            clear_sensor_readiness()
            logger.warning(
                "Warehouse scan preflight refused stale go-preflight reuse; "
                "failure_code=%s missing=%s unhealthy=%s",
                quick.failure_code,
                list(quick.missing_required_topics),
                list(quick.unhealthy_topics),
            )
            return quick
        clear_sensor_readiness()
        return reused

    stable_required_ms = _int_env("WAREHOUSE_PERCEPTION_REQUIRED_STABLE_MS", 8000)
    consecutive_required = max(
        1,
        _int_env(
            "WAREHOUSE_PREFLIGHT_CONSECUTIVE_CHECKS",
            max(3, stable_required_ms // 2000),
        ),
    )
    stable_required_s = stable_required_ms / 1000.0
    check_interval_s = max(1.0, _float_env("WAREHOUSE_PREFLIGHT_CHECK_INTERVAL_S", 1.5))
    wait_s = timeout_s if timeout_s is not None else _float_env(
        "WAREHOUSE_PREFLIGHT_PERCEPTION_WAIT_S", 45.0
    )

    port = build_warehouse_perception_port()
    deadline = time.monotonic() + max(5.0, wait_s)
    consecutive_ok = 0
    stable_started_at: float | None = None
    forced_once = False
    last = WarehouseReadinessResult(
        bridge_alive=False,
        ros_graph_ready=False,
        can_localize=False,
        can_perceive_depth=False,
        can_perceive_rgb=False,
        can_scan_lidar=False,
        can_build_map=False,
        can_avoid_obstacles=False,
        can_fly_warehouse_scan=False,
        failure_code="warehouse_sensors_not_ready",
        user_message="Waiting for warehouse sensor readiness",
        developer_message="preflight in progress",
    )

    while time.monotonic() < deadline:
        use_force = not forced_once
        if use_force:
            forced_once = True
            status = await _fetch_status(port, deep=True, force=True)
        else:
            status = await _fetch_status(port, deep=True, force=False)

        components = status.components if isinstance(status.components, dict) else {}
        if components.get("probe_in_progress"):
            await asyncio.sleep(check_interval_s)
            continue

        last = readiness_from_perception_status_strict(
            status,
            require_nvblox_for_map=require_nvblox_for_map,
        )

        if _preflight_sample_usable(last, components):
            if stable_started_at is None:
                stable_started_at = time.monotonic()
            stable_elapsed_s = time.monotonic() - stable_started_at
            consecutive_ok += 1
            logger.info(
                "Warehouse scan preflight consecutive_ok=%s/%s stable_s=%.1f/%.1f "
                "from_cache=%s probe_mode=%s",
                consecutive_ok,
                consecutive_required,
                stable_elapsed_s,
                stable_required_s,
                last.from_cache,
                last.probe_mode,
            )
            if consecutive_ok >= consecutive_required and stable_elapsed_s >= stable_required_s:
                record_sensor_readiness(ready=True, payload=last.to_dict())
                return last
        else:
            consecutive_ok = 0
            stable_started_at = None
            clear_sensor_readiness()
            logger.info(
                "Warehouse scan preflight not ready failure_code=%s missing=%s unhealthy=%s "
                "probe_mode=%s topic_count=%s",
                last.failure_code,
                list(last.missing_required_topics),
                list(last.unhealthy_topics),
                last.probe_mode,
                components.get("ros_topic_count"),
            )

        await asyncio.sleep(check_interval_s)

    logger.warning(
        "Warehouse scan preflight timed out after %.0fs failure_code=%s",
        wait_s,
        last.failure_code,
    )
    return last
