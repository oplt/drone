from __future__ import annotations

import asyncio
import logging
import time

from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_service import (
    WarehouseFlightMissionContext,
    WarehouseFlightReadinessSnapshot,
    evaluate_warehouse_flight_readiness,
)

logger = logging.getLogger(__name__)


async def ensure_warehouse_perception_stable(
    *,
    mission: WarehouseFlightMissionContext | None = None,
    timeout_s: float | None = None,
) -> WarehouseFlightReadinessSnapshot:
    """Block until core perception passes continuously for the configured duration."""
    config = WarehouseFlightConfig.from_env()
    required_ms = config.perception_required_stable_ms
    poll_s = max(0.2, float(config.perception_required_stable_ms) / 1000.0 / 16.0)
    poll_s = min(poll_s, 1.0)
    wait_s = timeout_s if timeout_s is not None else max(
        20.0,
        (required_ms / 1000.0) + 15.0,
    )
    deadline = time.monotonic() + wait_s
    last = await evaluate_warehouse_flight_readiness(mission=mission, force=True)

    while time.monotonic() < deadline:
        last = await evaluate_warehouse_flight_readiness(mission=mission, force=True)
        stable_ms = last.readiness.perception_stable_for_ms
        if last.readiness.ready_for_autonomy:
            logger.info(
                "Warehouse perception stable for %sms (required=%sms)",
                stable_ms,
                required_ms,
            )
            return last
        if (
            stable_ms >= required_ms
            and last.readiness.ready_to_takeoff
        ):
            logger.info(
                "Warehouse perception core stable for %sms (required=%sms)",
                stable_ms,
                required_ms,
            )
            return last
        await asyncio.sleep(poll_s)

    logger.warning(
        "Warehouse perception stability timed out after %.0fs stable_ms=%s required_ms=%s blocking=%s",
        wait_s,
        last.readiness.perception_stable_for_ms,
        required_ms,
        last.readiness.blocking_reasons,
    )
    return last
