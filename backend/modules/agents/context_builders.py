from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agents.schemas import AgentContext, AgentPhase
from backend.modules.missions.runtime_models import MissionRuntime
from backend.modules.patrol.models import PatrolDetection, PatrolIncident
from backend.modules.property_patrol.models import PropertyPatrolIncident, PropertyPatrolSite
from backend.modules.warehouse.models import (
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseMap,
    WarehouseScanTarget,
)
from backend.modules.warehouse.service.structure_jobs import get_extraction_state


async def build_patrol_incident_context(
    db: AsyncSession,
    *,
    incident_id: int,
) -> dict[str, Any]:
    incident = await db.get(PatrolIncident, incident_id)
    if incident is None:
        raise ValueError(f"Patrol incident {incident_id} not found")
    detection = None
    if incident.last_detection_id is not None:
        detection = await db.get(PatrolDetection, incident.last_detection_id)
    return {
        "incident": {
            "id": incident.id,
            "flight_id": incident.flight_id,
            "status": incident.status,
            "mission_task_type": incident.mission_task_type,
            "incident_type": incident.incident_type,
            "ai_task": incident.ai_task,
            "zone_name": incident.zone_name,
            "peak_confidence": incident.peak_confidence,
            "detection_count": incident.detection_count,
            "snapshot_path": incident.snapshot_path,
            "clip_path": incident.clip_path,
            "summary": incident.summary,
        },
        "detection": {
            "object_class": detection.object_class if detection else None,
            "confidence": detection.confidence if detection else None,
            "anomaly_type": detection.anomaly_type if detection else None,
            "track_id": detection.track_id if detection else None,
        },
    }


async def build_property_patrol_incident_context(
    db: AsyncSession,
    *,
    incident_id: int,
) -> dict[str, Any]:
    incident = await db.get(PropertyPatrolIncident, incident_id)
    if incident is None:
        raise ValueError(f"Property patrol incident {incident_id} not found")
    site = await db.get(PropertyPatrolSite, incident.site_id)
    return {
        "incident": {
            "id": incident.id,
            "site_id": incident.site_id,
            "site_name": site.name if site else None,
            "source": incident.source,
            "event_type": incident.event_type,
            "severity": incident.severity,
            "confidence": incident.confidence,
            "zone_id": incident.zone_id,
            "detected_objects": incident.detected_objects,
            "location": incident.location,
            "video_clip_id": incident.video_clip_id,
            "snapshot_ids": incident.snapshot_ids,
            "status": incident.status,
        },
    }


async def build_warehouse_scan_context(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    capture_result: dict[str, Any] | None = None,
    client_flight_id: str | None = None,
) -> dict[str, Any]:
    warehouse_map = await db.get(WarehouseMap, warehouse_map_id)
    if warehouse_map is None:
        raise ValueError(f"Warehouse map {warehouse_map_id} not found")

    target_count = await db.scalar(
        select(func.count())
        .select_from(WarehouseScanTarget)
        .where(
            WarehouseScanTarget.warehouse_map_id == warehouse_map_id,
            WarehouseScanTarget.active.is_(True),
        )
    )
    structure = get_extraction_state(warehouse_map_id)
    payload: dict[str, Any] = {
        "warehouse_map": {
            "id": warehouse_map.id,
            "name": warehouse_map.name,
        },
        "active_target_count": int(target_count or 0),
        "structure_extraction": structure,
    }
    if capture_result:
        payload["capture_result"] = capture_result
    if client_flight_id:
        payload["client_flight_id"] = client_flight_id
    return payload


async def build_warehouse_inspection_context(
    db: AsyncSession,
    *,
    inspection_mission_id: int,
) -> dict[str, Any]:
    mission = await db.get(WarehouseInspectionMission, inspection_mission_id)
    if mission is None:
        raise ValueError(f"Inspection mission {inspection_mission_id} not found")
    results = (
        await db.execute(
            select(WarehouseInspectionResult).where(
                WarehouseInspectionResult.mission_id == inspection_mission_id
            )
        )
    ).scalars().all()
    status_counts: dict[str, int] = {}
    for row in results:
        status_counts[str(row.status)] = status_counts.get(str(row.status), 0) + 1
    return {
        "inspection_mission": {
            "id": mission.id,
            "warehouse_map_id": mission.warehouse_map_id,
            "status": mission.status,
            "scan_mode": mission.scan_mode,
            "target_count": len(mission.target_ids_json or []),
        },
        "result_counts": status_counts,
        "results": [
            {
                "target_id": row.target_id,
                "status": row.status,
                "expected_barcode": row.expected_barcode,
                "detected_barcode": row.detected_barcode,
                "confidence": row.confidence,
                "error_message": row.error_message,
            }
            for row in results[:50]
        ],
    }


async def build_field_survey_context(
    db: AsyncSession,
    *,
    mission_runtime_id: int | None = None,
    client_flight_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = None
    if mission_runtime_id is not None:
        runtime = await db.get(MissionRuntime, mission_runtime_id)
    elif client_flight_id:
        runtime = await db.scalar(
            select(MissionRuntime).where(MissionRuntime.client_flight_id == client_flight_id)
        )
    payload: dict[str, Any] = {}
    if runtime is not None:
        payload["mission_runtime"] = {
            "id": runtime.id,
            "client_flight_id": runtime.client_flight_id,
            "mission_name": runtime.mission_name,
            "mission_type": runtime.mission_type,
            "state": runtime.state,
            "mission_params": runtime.mission_params,
            "last_error": runtime.last_error,
        }
    if extra:
        payload.update(extra)
    return payload


async def build_livestock_plan_context(
    db: AsyncSession,
    *,
    task_id: int,
    mission_plan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "livestock_task": {"id": task_id},
        "mission_plan": mission_plan,
    }
