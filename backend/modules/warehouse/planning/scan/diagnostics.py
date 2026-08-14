from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from backend.core.config.runtime import settings
from backend.modules.warehouse.planning.scan_geometry import (
    WarehouseExecutionFrame,
    active_mapping_startup_timing,
    angle_delta_deg as _angle_delta_deg,
    begin_mapping_startup_timing as _begin_mapping_startup_timing,
    dedupe_preserving_order as _dedupe_preserving_order,
    interpolate_yaw_deg as _interpolate_yaw_deg,
    normalize_angle_deg as _normalize_angle_deg,
    note_mapping_startup as _note_mapping_startup,
    safe_token_value as _safe_token,
)
from backend.infrastructure.runtime.blocking import run_blocking
from backend.infrastructure.camera.runtime import shared_video_runtime
from backend.infrastructure.vehicle.frame_conversion import local_ned_position_to_enu
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.schemas.mission_types import SIM_WAREHOUSE_LOCAL_ORIGIN
from backend.modules.vehicle_runtime.types import Coordinate, EnuCoordinate
from backend.modules.warehouse.exceptions import WarehouseMissionFailure
from backend.modules.warehouse.planning.local_planner import (
    WarehouseDockConfig,
    WarehouseLaneStrategy,
    WarehouseLocalPoint,
    WarehousePlanResult,
    WarehousePlanSegment,
    WarehouseScanPattern,
    WarehouseViewMode,
    plan_warehouse_scan,
)
from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
    WarehousePerceptionPort,
)
from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow
from backend.modules.warehouse.service.capture import WarehouseCaptureSessionService
from backend.modules.warehouse.service.mapping import WarehouseScanMappingService
from backend.modules.warehouse.service.runtime_safety import WarehouseRuntimeSafetyTracker
from backend.modules.warehouse.service.video import (
    warehouse_video_recording_enabled,
    warehouse_video_skip_reason,
)

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class WarehouseScanDiagnosticsMixin:
    async def _collect_mission_diagnostics(
        self,
        orch: Orchestrator,
        *,
        phase: str,
    ) -> dict[str, object]:
        from backend.modules.warehouse.service.readiness_result import (
            readiness_from_perception_status_strict,
        )
        from backend.modules.warehouse.service.warehouse_preflight import (
            fetch_warehouse_perception_status,
        )

        del orch
        # After cleanup the mapping stack + ROS bridge are already torn down, so a
        # deep/forced probe just burns seconds on _ensure_ros_bridge_running +
        # `ros2 topic list` timeouts (and would try to restart the bridge). Use a
        # shallow, non-forcing probe for the post-cleanup snapshot.
        is_post_cleanup = phase == "post_cleanup"
        try:
            status = await fetch_warehouse_perception_status(
                deep=not is_post_cleanup,
                force=not is_post_cleanup,
            )
            readiness = readiness_from_perception_status_strict(status)
        except Exception as exc:
            logger.warning("Mission diagnostic health probe failed (%s): %s", phase, exc)
            return {"phase": phase, "probe_failed": True}

        return {
            "phase": phase,
            "bridge_alive": readiness.bridge_alive,
            "ros_graph_ready": readiness.ros_graph_ready,
            "can_localize": readiness.can_localize,
            "missing_required_topics": list(readiness.missing_required_topics),
            "missing_nvblox_topics": list(readiness.missing_nvblox_topics),
            "unhealthy_topics": list(readiness.unhealthy_topics),
        }

    def _latest_odometry_drift(self, orch: Orchestrator) -> float | None:
        snapshot = getattr(orch, "_last_telemetry_snapshot", None)
        if not isinstance(snapshot, dict):
            return None
        raw = snapshot.get("odometry_drift_m")
        try:
            return round(float(raw), 3) if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def _log_mission_diagnostic_summary(
        self,
        orch: Orchestrator,
        *,
        mission_error: Exception | None,
        mapping_saved: bool,
        phase: str = "pre_cleanup",
    ) -> None:
        from backend.modules.warehouse.exceptions import WarehouseMissionFailure

        failure_code = None
        if isinstance(mission_error, WarehouseMissionFailure):
            failure_code = mission_error.reason

        diagnostics = await self._collect_mission_diagnostics(orch, phase=phase)

        summary: dict[str, object] = {
            "flight_id": getattr(orch, "_flight_id", None),
            "mission_type": self.mission_kind,
            "diagnostics_phase": phase,
            "result": (
                "failed"
                if mission_error
                else ("partial_failure" if not mapping_saved else "completed")
            ),
            "failure_code": failure_code,
            "mapping_saved": mapping_saved,
            "cleanup_completed": phase == "post_cleanup",
        }
        client_flight_id = self._flight_token(orch)
        from backend.modules.warehouse.service.live_map_manifest import (
            load_flight_manifest,
        )

        manifest = load_flight_manifest(client_flight_id)
        if manifest is not None:
            summary["live_map_manifest"] = manifest.as_dict()
            summary["quality_evidence"] = manifest.quality_evidence
            summary["localization_quality"] = manifest.localization_quality
            summary["map_quality"] = manifest.map_quality
            summary["rack_face_coverage"] = manifest.rack_face_coverage
            summary["coverage_repair"] = manifest.coverage_repair
        if diagnostics.get("probe_failed"):
            summary["probe_failed"] = True
        else:
            summary.update(
                {
                    "bridge_alive": diagnostics.get("bridge_alive"),
                    "ros_graph_ready": diagnostics.get("ros_graph_ready"),
                    "can_localize": diagnostics.get("can_localize"),
                    "missing_required_topics": diagnostics.get("missing_required_topics"),
                    "missing_nvblox_topics": diagnostics.get("missing_nvblox_topics"),
                    "unhealthy_topics": diagnostics.get("unhealthy_topics"),
                }
            )
            if manifest is None and phase == "post_cleanup":
                summary["quality_evidence"] = False
            elif manifest is not None and manifest.quality_evidence:
                summary["quality_evidence"] = True
                if not diagnostics.get("can_localize"):
                    summary["localization_quality"] = "degraded"

        logger.info("Warehouse mission diagnostic summary %s", summary)
        await self._add_event_safe(orch, "warehouse_mission_diagnostic", summary)

    async def _check_runtime_safety(self, orch: Orchestrator) -> None:
        deep = self._runtime_safety.should_run_deep_health_probe()
        try:
            status = await build_warehouse_perception_port().status(
                deep=deep,
                force=False,
            )
        except Exception as exc:
            logger.warning("Warehouse runtime safety health check failed: %s", exc)
            return
        if deep:
            self._runtime_safety.mark_deep_probe_ran()

        components = status.components if isinstance(status.components, dict) else {}
        components = dict(components)
        from backend.modules.warehouse.service.runtime_safety import read_odometry_state_file

        odom_read = read_odometry_state_file()
        if odom_read.unreadable:
            components["odometry_state_unreadable"] = True
            components["local_odometry_state"] = {}
        elif odom_read.payload:
            components["local_odometry_state"] = odom_read.payload
        from backend.modules.warehouse.service.runtime_safety import (
            merge_runtime_odometry_components,
        )

        components = merge_runtime_odometry_components(components)
        decision = self._runtime_safety.evaluate(
            components,
            deep_health=deep,
            min_localization_confidence=float(self.localization_confidence_min),
            min_obstacle_distance_m=float(self.clearance_m),
            min_ceiling_distance_m=float(self.ceiling_margin_m),
        )
        from backend.modules.warehouse.service.flight_watchdog import (
            apply_watchdog_to_safety_decision,
            get_warehouse_flight_watchdog,
        )

        watchdog = get_warehouse_flight_watchdog()
        if not watchdog.active:
            watchdog.start()
        watchdog_action = watchdog.evaluate(components=components, status=status)
        if watchdog_action.triggered:
            decision = apply_watchdog_to_safety_decision(watchdog_action)
        if decision.safe:
            return
        await self._add_event_safe(
            orch,
            "warehouse_safety_abort",
            {
                "reason": decision.reason,
                "action": decision.action,
                "details": decision.details or {},
                "deep_health": deep,
            },
        )
        raise WarehouseMissionFailure(
            reason=decision.reason or "warehouse_safety_abort",
            action=decision.action,
            stage="flight",
            message=f"Warehouse safety abort: {decision.reason}",
            details=decision.details or {},
        )
