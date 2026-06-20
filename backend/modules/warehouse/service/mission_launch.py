from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.missions.flight_profile import FlightEnvironment
from backend.modules.missions.schemas.mission_create import MissionCreateIn
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.missions.service.mission_start import start_mission_for_user
from backend.modules.organizations.service import can_access_org_scope
from backend.modules.warehouse.models import WarehouseDockStation, WarehouseMap
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.repository.settings import WarehouseSettingsRepository
from backend.modules.warehouse.schemas import WarehouseMissionDefaultsOut

_repo = WarehouseMappingRepository()
_settings_repo = WarehouseSettingsRepository()
_SETTINGS_SECTION = "warehouse"
_MISSION_DEFAULTS_KEY = "mission_defaults"


async def _read_warehouse_settings(db: AsyncSession) -> dict[str, Any]:
    data = await _settings_repo.read_document(db)
    section = data.get(_SETTINGS_SECTION)
    return dict(section) if isinstance(section, dict) else {}


async def _get_map_or_404(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    user: Any,
) -> WarehouseMap:
    warehouse_map = await _repo.get_owned_warehouse_map(
        db,
        warehouse_map_id=warehouse_map_id,
        owner_id=int(user.id),
        org_id=user.org_id,
        allow_org_access=can_access_org_scope(user),
    )
    if warehouse_map is None:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    return warehouse_map


async def _dock_config_for_mission(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    dock_id: int | None,
) -> dict[str, Any] | None:
    if dock_id is None:
        return None
    dock = (
        await db.execute(
            select(WarehouseDockStation).where(
                WarehouseDockStation.id == int(dock_id),
                WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                WarehouseDockStation.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if dock is None:
        raise HTTPException(status_code=404, detail="Warehouse dock station not found")
    meta = dock.meta_data if isinstance(dock.meta_data, dict) else {}
    return {
        "dock_pose": dock.pose_local_json,
        "entry_pose": dock.entry_pose_local_json,
        "exit_pose": dock.exit_pose_local_json,
        "marker_id": dock.marker_id,
        "dock_yaw_deg": meta.get("dock_yaw_deg"),
        "precision_required": bool(meta.get("precision_required", True)),
    }


async def build_warehouse_scan_mission_payload(
    db: AsyncSession,
    *,
    user: Any,
    warehouse_map_id: int,
    mission_name: str,
    sensor_rig_id: int | None,
    dock_id: int | None,
    reference_mapping_job_id: int | None,
    cruise_alt: float | None = None,
    work_speed_mps: float | None = None,
):
    warehouse_map = await _get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=user)
    settings_doc = await _read_warehouse_settings(db)
    defaults = WarehouseMissionDefaultsOut.model_validate(
        settings_doc.get(_MISSION_DEFAULTS_KEY) or {}
    )
    scan_payload = defaults.model_dump(mode="python")
    if cruise_alt is not None:
        scan_payload["cruise_alt"] = float(cruise_alt)
    if work_speed_mps is not None:
        scan_payload["work_speed_mps"] = float(work_speed_mps)

    base_height_m = float(scan_payload.pop("cruise_alt"))
    scan_payload.update(
        {
            "polygon_local_m": _repo.polygon_from_local(warehouse_map),
            "warehouse_map_id": int(warehouse_map.id),
            "warehouse_name": warehouse_map.name,
            "reference_mapping_job_id": reference_mapping_job_id,
            "sensor_rig_id": sensor_rig_id,
            "dock_config": await _dock_config_for_mission(
                db,
                warehouse_map_id=int(warehouse_map.id),
                dock_id=dock_id,
            ),
        }
    )
    mission_payload = MissionCreateIn(
        name=mission_name or "Warehouse Scan",
        cruise_alt=base_height_m,
        mission_type=MissionType.WAREHOUSE_SCAN,
        flight_environment=FlightEnvironment.INDOOR_LOCAL,
        warehouse_scan=scan_payload,
    )
    return warehouse_map, mission_payload, base_height_m


async def start_warehouse_scan_mission(
    *,
    db: AsyncSession,
    user: Any,
    warehouse_map_id: int,
    mission_name: str,
    sensor_rig_id: int | None,
    dock_id: int | None,
    reference_mapping_job_id: int | None,
    cruise_alt: float | None = None,
    work_speed_mps: float | None = None,
) -> dict[str, Any]:
    _warehouse_map, mission_payload, _base_height_m = await build_warehouse_scan_mission_payload(
        db,
        user=user,
        warehouse_map_id=warehouse_map_id,
        mission_name=mission_name,
        sensor_rig_id=sensor_rig_id,
        dock_id=dock_id,
        reference_mapping_job_id=reference_mapping_job_id,
        cruise_alt=cruise_alt,
        work_speed_mps=work_speed_mps,
    )
    result = await start_mission_for_user(mission_payload, user=user)
    return result.model_dump(mode="json")
