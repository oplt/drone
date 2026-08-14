from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class WarehouseExplorationFlyTeardownMixin:
    async def _fly_exploration_teardown(
        self,
        orch: Orchestrator,
        *,
        flight_token: str,
        perception_started: bool,
        mapping_stack_started: bool,
    ) -> None:
        if perception_started:
            from backend.modules.warehouse.service.capture_finalize import (
                persist_warehouse_ros_capture,
                stop_warehouse_ros_mapping,
            )
            from backend.modules.warehouse.service.mapping import WarehouseScanMappingError

            try:
                stop_result = await stop_warehouse_ros_mapping(flight_id=flight_token)
            except Exception as exc:
                stop_result = None
                await self._add_event_safe(
                    orch,
                    "indoor_exploration_mapping_stop_failed",
                    {"error": str(exc)},
                )
                logger.exception(
                    "Indoor exploration mapping stop failed flight_id=%s",
                    flight_token,
                )
            if stop_result is not None:
                await self._add_event_safe(
                    orch,
                    "indoor_exploration_mapping_stopped",
                    {
                        "accepted": stop_result.accepted,
                        "status": stop_result.status,
                        "detail": stop_result.detail,
                    },
                )
            if (
                stop_result is not None
                and stop_result.accepted
                and self.owner_id is not None
                and self.warehouse_map_id is not None
            ):
                stop_data = stop_result.data if isinstance(stop_result.data, dict) else None
                try:
                    mapping_result = await persist_warehouse_ros_capture(
                        flight_id=flight_token,
                        owner_id=int(self.owner_id),
                        org_id=None,
                        source="indoor_exploration",
                        stop_data=stop_data,
                        warehouse_map_id=int(self.warehouse_map_id),
                        warehouse_name=self.warehouse_name,
                        db_flight_id=getattr(orch, "_flight_id", None),
                        mission_kind="indoor_exploration",
                    )
                    await self._add_event_safe(
                        orch,
                        "indoor_exploration_mapping_saved",
                        mapping_result,
                    )
                except WarehouseScanMappingError as exc:
                    await self._add_event_safe(
                        orch,
                        "indoor_exploration_mapping_failed",
                        {"error": str(exc)},
                    )
                    logger.warning(
                        "Indoor exploration mapping persistence failed flight_id=%s error=%s",
                        flight_token,
                        exc,
                    )
        if mapping_stack_started:
            from backend.modules.warehouse.service.mapping_stack_lifecycle import (
                shutdown_warehouse_mapping_stack,
            )

            try:
                await shutdown_warehouse_mapping_stack()
            except Exception as exc:
                await self._add_event_safe(
                    orch,
                    "indoor_exploration_mapping_cleanup_failed",
                    {"error": str(exc)},
                )
                logger.warning("Indoor exploration mapping stack shutdown failed", exc_info=True)
