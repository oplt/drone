from __future__ import annotations

import asyncio
import logging
import os
import time

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


async def ensure_warehouse_scan_preflight(
    *,
    timeout_s: float | None = None,
    require_nvblox_for_map: bool = False,
) -> WarehouseReadinessResult:
    """Fresh deep health with N consecutive passing samples — never uses stale cache."""
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    stable_required_ms = _int_env("WAREHOUSE_PERCEPTION_REQUIRED_STABLE_MS", 8000)
    consecutive_required = max(
        1,
        _int_env(
            "WAREHOUSE_PREFLIGHT_CONSECUTIVE_CHECKS",
            max(10, stable_required_ms // 500),
        ),
    )
    stable_required_s = stable_required_ms / 1000.0
    stable_started_at: float | None = None
    check_interval_s = max(0.2, _float_env("WAREHOUSE_PREFLIGHT_CHECK_INTERVAL_S", 0.5))
    wait_s = timeout_s if timeout_s is not None else _float_env(
        "WAREHOUSE_PREFLIGHT_PERCEPTION_WAIT_S", 20.0
    )

    port = build_warehouse_perception_port()
    deadline = time.monotonic() + max(2.0, wait_s)
    consecutive_ok = 0
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
        status = await port.status(deep=True, force=True)
        components = status.components if isinstance(status.components, dict) else {}
        if components.get("from_cache") and not components.get("probe_mode", "").endswith("forced"):
            logger.warning(
                "Warehouse preflight received cached health; forcing another probe probe_mode=%s",
                components.get("probe_mode"),
            )
            status = await port.status(deep=True, force=True)

        if components.get("probe_in_progress") and not components.get("cache_ready"):
            await asyncio.sleep(check_interval_s)
            continue

        last = readiness_from_perception_status_strict(
            status,
            require_nvblox_for_map=require_nvblox_for_map,
        )
        if last.from_cache:
            logger.warning(
                "Warehouse preflight ignoring cached sample probe_mode=%s",
                last.probe_mode,
            )
            consecutive_ok = 0
            await asyncio.sleep(check_interval_s)
            continue

        if last.can_fly_warehouse_scan:
            if stable_started_at is None:
                stable_started_at = time.monotonic()
            stable_elapsed_s = time.monotonic() - stable_started_at
            consecutive_ok += 1
            logger.info(
                "Warehouse preflight consecutive_ok=%s/%s stable_s=%.1f/%.1f bridge=%s localize=%s depth=%s rgb=%s",
                consecutive_ok,
                consecutive_required,
                stable_elapsed_s,
                stable_required_s,
                last.bridge_alive,
                last.can_localize,
                last.can_perceive_depth,
                last.can_perceive_rgb,
            )
            if consecutive_ok >= consecutive_required and stable_elapsed_s >= stable_required_s:
                return last
        else:
            consecutive_ok = 0
            stable_started_at = None
            logger.info(
                "Warehouse preflight not ready failure_code=%s missing=%s unhealthy=%s",
                last.failure_code,
                list(last.missing_required_topics),
                list(last.unhealthy_topics),
            )

        await asyncio.sleep(check_interval_s)

    logger.warning(
        "Warehouse scan preflight timed out after %.0fs failure_code=%s",
        wait_s,
        last.failure_code,
    )
    return last
