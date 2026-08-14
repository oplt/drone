from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from backend.modules.missions.flight_models import FlightStatus
from backend.modules.warehouse.exceptions import WarehouseMissionFailure
from backend.modules.warehouse.planning.local_planner import WarehousePlanResult
from backend.modules.warehouse.service.capture import WarehouseCaptureSessionService
from backend.modules.warehouse.service.mapping import WarehouseScanMappingService

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class WarehouseScanFlyScanCompleteMixin:
    async def _fly_scan_persist_and_complete(
        self,
        orch: Orchestrator,
        *,
        session,
        plan: WarehousePlanResult,
        mission_error: Exception | None,
        capture_session_service: WarehouseCaptureSessionService,
        mapping_service: WarehouseScanMappingService,
        video_recording_active: bool,
    ) -> tuple[bool, Exception | None]:
        mapping_saved = False
        mapping_error: Exception | None = None
        if mission_error is None:
            try:
                perception_paths = await self._download_perception_artifacts(
                    orch,
                    destination_dir=session.session_dir,
                )
                fallback_paths = await self._download_capture_if_supported(
                    orch,
                    destination_dir=str(session.session_dir),
                )
                capture_paths = [*perception_paths, *fallback_paths]
                imported_direct = await capture_session_service.import_external_files_async(
                    session,
                    capture_paths=capture_paths,
                )
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_direct_download",
                    {
                        "downloaded_paths_count": len(capture_paths),
                        "imported_count": imported_direct,
                    },
                )

                sync_trigger = await capture_session_service.trigger_external_sync_async(
                    session,
                )
                await self._add_event_safe(orch, "warehouse_scan_external_sync", sync_trigger)

                sync_result = await capture_session_service.finalize_session_async(
                    session,
                    min_files=self.capture_min_files if self.await_capture_sync else 0,
                    timeout_s=self.capture_sync_wait_timeout_s if self.await_capture_sync else 0.0,
                    poll_interval_s=self.capture_sync_poll_interval_s,
                    extra_meta={
                        "mission_kind": self.mission_kind,
                        "work_speed_mps": self.work_speed_mps,
                        "transit_speed_mps": self.transit_speed_mps,
                        "scan_pattern": self.scan_pattern,
                        "view_mode": self.view_mode,
                        "layer_count": self.layer_count,
                        "warehouse_map_id": self.warehouse_map_id,
                        "sensor_rig_id": self.sensor_rig_id,
                        "reference_mapping_job_id": self.reference_mapping_job_id,
                        "perception_artifacts_count": len(perception_paths),
                        "direct_downloaded_paths_count": len(fallback_paths),
                        "direct_import_count": imported_direct,
                        "rosbag_paths": [
                            str(Path(path).name)
                            for path in perception_paths
                            if Path(path).suffix.lower() in {".db3", ".mcap", ".bag"}
                        ],
                    },
                    operation="warehouse_capture_finalize",
                    call_timeout_s=max(1.0, self.capture_sync_wait_timeout_s + 30.0),
                )
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_capture_staged",
                    {
                        "source_dir": sync_result.get("source_dir"),
                        "file_count": sync_result.get("file_count", 0),
                        "status": sync_result.get("status"),
                    },
                )

                required_capture_files = max(1, int(self.capture_min_files))
                actual_capture_files = int(sync_result.get("file_count", 0) or 0)
                if actual_capture_files < required_capture_files:
                    raise RuntimeError(
                        "Warehouse scan capture is incomplete. "
                        f"Received {actual_capture_files} files; at least "
                        f"{required_capture_files} are required for 3D map persistence."
                    )

                if self.owner_id is None:
                    raise RuntimeError(
                        "Warehouse scan owner_id is required to persist captured warehouse maps."
                    )

                client_flight_id = self._flight_token(orch)
                sync_result["client_flight_id"] = client_flight_id

                from backend.modules.warehouse.service.live_map_manifest import (
                    build_manifest_from_flight_dir,
                    finalize_manifest_integrity,
                    save_flight_manifest,
                    validate_save_quality,
                )

                pre_shutdown_diagnostics = await self._collect_mission_diagnostics(
                    orch,
                    phase="pre_finalize",
                )
                manifest_missing_topics = list(
                    pre_shutdown_diagnostics.get("missing_required_topics", [])
                ) + list(pre_shutdown_diagnostics.get("missing_nvblox_topics", []))
                manifest_localization_ok = bool(
                    pre_shutdown_diagnostics.get("can_localize")
                )

                def _build_save_validate_manifest():
                    # build_manifest_from_flight_dir scans + hashes every chunk file
                    # on disk (O(total bytes)); running it inline blocks the event
                    # loop for seconds during teardown. Offload the whole sync block
                    # to a worker thread so live WS clients / other flights keep moving.
                    built = build_manifest_from_flight_dir(
                        client_flight_id,
                        missing_topics=manifest_missing_topics,
                        localization_ok=manifest_localization_ok,
                        diagnostics_phase="pre_finalize",
                    )
                    built = finalize_manifest_integrity(built)
                    save_flight_manifest(built)
                    ok, detail = validate_save_quality(built)
                    return built, ok, detail

                manifest, save_ok, save_detail = await asyncio.to_thread(
                    _build_save_validate_manifest
                )
                sync_result["live_map_manifest"] = manifest.as_dict()
                sync_result["live_map_quality"] = {
                    "ok": save_ok,
                    "detail": save_detail,
                    "map_quality": manifest.map_quality,
                    "manifest_status": manifest.manifest_status,
                    "chunk_counts": dict(manifest.chunk_counts),
                    "point_counts": dict(manifest.point_counts),
                    "missing_topics": list(manifest.missing_topics),
                    "nvblox_available": manifest.nvblox_available,
                }
                live_map_chunk_total = sum(int(v) for v in manifest.chunk_counts.values())
                sync_result["live_map_chunk_total"] = live_map_chunk_total
                sync_result["live_map_manifest_status"] = manifest.manifest_status
                logger.info(
                    "Warehouse scan map readiness: capture_session_files=%s "
                    "live_map_chunks=%s manifest_status=%s nvblox_available=%s",
                    sync_result.get("file_count"),
                    live_map_chunk_total,
                    manifest.manifest_status,
                    manifest.nvblox_available,
                )
                if not save_ok:
                    raise RuntimeError(save_detail)
                sync_result["status"] = "ready"
                if not manifest.nvblox_available:
                    sync_result["status"] = "degraded"
                    sync_result["degradation_reason"] = "nvblox_unavailable"

                db_flight_id = getattr(orch, "_flight_id", None)
                if db_flight_id is not None:
                    sync_result["flight_id"] = db_flight_id

                mapping_result = await mapping_service.persist_capture(
                    owner_id=int(self.owner_id),
                    org_id=None,
                    warehouse_map_id=self.warehouse_map_id,
                    warehouse_name=self.warehouse_name,
                    polygon_local_m=list(self.area_polygon_local_m or []),
                    session_dir=session.session_dir,
                    capture_result=sync_result,
                    reference_mapping_job_id=self.reference_mapping_job_id,
                    flight_id=getattr(orch, "_flight_id", None),
                )
                mapping_saved = True
                await self._add_event_safe(orch, "warehouse_scan_mapping_saved", mapping_result)
                if client_flight_id:
                    from backend.modules.warehouse.service.live_map_stream import (
                        warehouse_live_map_stream,
                    )

                    job_id = mapping_result.get("job_id")
                    await warehouse_live_map_stream.finalize(
                        str(client_flight_id),
                        int(job_id) if job_id is not None else None,
                    )
                try:
                    from backend.modules.agents.hooks import schedule_warehouse_scan_postflight

                    schedule_warehouse_scan_postflight(
                        warehouse_map_id=int(self.warehouse_map_id),
                        client_flight_id=client_flight_id,
                        capture_result=dict(sync_result),
                    )
                except Exception:
                    logger.exception("Failed to schedule warehouse scan agent postflight")

            except Exception as exc:
                mapping_error = exc
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_mapping_failed",
                    {"error": str(exc)},
                )
                logger.exception("Warehouse scan mapping persistence failed")
        else:
            await self._add_event_safe(
                orch,
                "warehouse_scan_mapping_skipped",
                {"reason": "flight_failed", "error": str(mission_error)},
            )

        final_status = FlightStatus.COMPLETED if mission_error is None else FlightStatus.FAILED
        ros_mapping_status = "completed" if mapping_saved else (
            "failed" if mapping_error is not None else "skipped"
        )
        artifact_export_status = "exported" if mapping_saved else (
            "missing_outputs" if mapping_error is not None else "not_attempted"
        )
        overall_status = "completed"
        if mission_error is not None:
            overall_status = "failed"
        elif mapping_error is not None:
            overall_status = "partial_failure"

        if mission_error is not None:
            final_note = "Warehouse scan flight failed; 3D map persistence was skipped"
        elif mapping_saved:
            final_note = "Warehouse scan flight completed and 3D map persisted"
        elif mapping_error is not None:
            final_note = (
                "Flight completed, but warehouse mapping failed because no ROS mapping "
                f"artifacts were produced: {str(mapping_error)[:160]}"
            )
        else:
            final_note = "Warehouse scan flight completed"

        await self._finish_flight_safe(orch, status=final_status, note=final_note)

        await self._add_event_safe(
            orch,
            "warehouse_scan_complete",
            {
                "segments": len(plan.segments),
                "work_legs": sum(1 for s in plan.segments if s.work_leg),
                "route_m": round(float(plan.stats.get("route_m", 0.0) or 0.0), 1),
                "mapping_saved": mapping_saved,
                "mapping_error": str(mapping_error) if mapping_error is not None else None,
                "flight_status": final_status.value,
                "video_capture_status": "completed" if video_recording_active else "not_started",
                "ros_mapping_status": ros_mapping_status,
                "artifact_export_status": artifact_export_status,
                "overall_status": overall_status,
                "scan_pattern": self.scan_pattern,
                "view_mode": self.view_mode,
                "layers": int(self.layer_count),
                "odometry_drift_m": self._latest_odometry_drift(orch),
            },
        )

        from backend.modules.warehouse.service.mapping_stack_lifecycle import (
            shutdown_warehouse_mapping_stack,
        )

        await self._log_mission_diagnostic_summary(
            orch,
            mission_error=mission_error,
            mapping_saved=mapping_saved,
            phase="pre_cleanup",
        )

        await self._mark_mission_runtime_terminal_safe(
            orch,
            mission_error=mission_error,
            mapping_error=mapping_error,
            mapping_saved=mapping_saved,
        )

        try:
            await shutdown_warehouse_mapping_stack()
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "warehouse_scan_cleanup_failed",
                {"error": str(exc)},
            )
            logger.warning("Warehouse mapping cleanup failed", exc_info=True)

        await self._log_mission_diagnostic_summary(
            orch,
            mission_error=mission_error,
            mapping_saved=mapping_saved,
            phase="post_cleanup",
        )

        if mission_error is not None:
            raise mission_error
        if mapping_error is not None:
            raise WarehouseMissionFailure(
                reason="mapping_artifacts_missing",
                action="complete",
                stage="capture",
                message=(
                    "Flight completed, but warehouse mapping failed because no ROS mapping "
                    "artifacts were produced. Check RGB/depth/odometry/nvblox topics "
                    "before rerunning."
                ),
                details={
                    "mapping_error": str(mapping_error)[:500],
                    "overall_status": "partial_failure",
                    "artifact_export_status": "missing_outputs",
                },
            )
        return mapping_saved, mapping_error
