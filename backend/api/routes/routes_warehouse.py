from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes import routes_flights
from backend.flight.missions.warehouse_mission import (
    WarehouseMissionDefaults,
    WarehouseMissionDefaultsPatch,
    WarehouseDockConfigParams,
    WarehouseDockPoseParams,
    WarehouseScanMissionParams,
    merge_warehouse_mission_defaults,
)
from backend.auth.deps import require_user
from backend.db.models import SettingsRow, WarehouseAsset, WarehouseMap, WarehouseMappingJob, WarehouseModel
from backend.db.repository.warehouse_mapping_repo import WarehouseMappingRepository
from backend.db.session import get_db
from backend.flight.missions.schemas import MissionType
from backend.flight.missions.warehouse_local_planner import (
    WarehouseDockConfig,
    WarehouseLocalPoint,
)


router = APIRouter(prefix="/warehouse", tags=["warehouse"])
logger = logging.getLogger(__name__)
repo = WarehouseMappingRepository()

_WAREHOUSE_SETTINGS_SECTION = "warehouse"
_WAREHOUSE_MISSION_DEFAULTS_KEY = "mission_defaults"


# ------------------------------------------------------------------ schemas

class WarehouseScanStartIn(WarehouseMissionDefaultsPatch):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = Field(default="Warehouse Scan", min_length=1, max_length=120)
    reference_mapping_job_id: Optional[int] = Field(default=None, ge=1)


class WarehouseMissionLaunchOut(BaseModel):
    warehouse_map_id: int
    warehouse_name: str
    preflight: routes_flights.PreflightRunOut
    mission: routes_flights.MissionCreateOut


class WarehouseScannedMapAssetOut(BaseModel):
    id: int
    type: str
    url: str
    created_at: datetime
    meta_data: Dict[str, Any] = Field(default_factory=dict)


class WarehouseScannedMapOut(BaseModel):
    job_id: int
    model_id: int
    model_version: int
    warehouse_map_id: int
    warehouse_name: str
    status: str
    created_at: datetime
    finished_at: Optional[datetime] = None
    polygon_local_m: list[list[float]] = Field(default_factory=list)
    assets: List[WarehouseScannedMapAssetOut] = Field(default_factory=list)


class WarehouseMapCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    # Option A – simple rectangle: supply width and length in metres
    width_m: Optional[float] = Field(default=None, gt=0.0, le=500.0)
    length_m: Optional[float] = Field(default=None, gt=0.0, le=500.0)
    # Option B – explicit polygon in the local metric frame [[x_m, y_m], ...]
    polygon_local_m: Optional[list[list[float]]] = Field(default=None, min_length=3)

    @model_validator(mode="after")
    def _resolve_polygon(self) -> "WarehouseMapCreateIn":
        if self.polygon_local_m is not None:
            return self
        if self.width_m is not None and self.length_m is not None:
            w, l = float(self.width_m), float(self.length_m)
            self.polygon_local_m = [[0.0, 0.0], [w, 0.0], [w, l], [0.0, l]]
            return self
        raise ValueError(
            "Supply either polygon_local_m, or both width_m and length_m."
        )


class WarehouseMapOut(BaseModel):
    id: int
    name: str
    area_m2: Optional[float]
    created_at: datetime
    polygon_local_m: list[list[float]] = Field(default_factory=list)


class WarehouseDockLocalPose(BaseModel):
    x_m: float
    y_m: float
    z_m: float
    yaw_deg: Optional[float] = None


class WarehouseDockCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    pose: WarehouseDockLocalPose
    entry_pose: WarehouseDockLocalPose
    exit_pose: WarehouseDockLocalPose
    marker_id: Optional[str] = Field(default=None, max_length=128)
    charger_type: Optional[str] = Field(default=None, max_length=64)
    precision_required: bool = True


class WarehouseDockOut(BaseModel):
    id: int
    name: str
    marker_id: Optional[str]
    charger_type: Optional[str]
    pose: WarehouseDockLocalPose
    entry_pose: WarehouseDockLocalPose
    exit_pose: WarehouseDockLocalPose
    active: bool
    created_at: datetime


# ------------------------------------------------------------------ helpers

def _extract_warehouse_mission_defaults(data: Any) -> WarehouseMissionDefaults:
    if not isinstance(data, dict):
        return WarehouseMissionDefaults()
    warehouse = data.get(_WAREHOUSE_SETTINGS_SECTION)
    if not isinstance(warehouse, dict):
        return WarehouseMissionDefaults()
    raw_defaults = warehouse.get(_WAREHOUSE_MISSION_DEFAULTS_KEY)
    if not isinstance(raw_defaults, dict):
        return WarehouseMissionDefaults()
    try:
        return WarehouseMissionDefaults.model_validate(raw_defaults)
    except ValidationError:
        logger.warning("Invalid stored warehouse mission defaults. Falling back to built-in values.")
        return WarehouseMissionDefaults()


def _with_warehouse_mission_defaults(data: Any, defaults: WarehouseMissionDefaults) -> dict[str, Any]:
    settings_data = dict(data) if isinstance(data, dict) else {}
    warehouse = settings_data.get(_WAREHOUSE_SETTINGS_SECTION)
    warehouse_data = dict(warehouse) if isinstance(warehouse, dict) else {}
    warehouse_data[_WAREHOUSE_MISSION_DEFAULTS_KEY] = defaults.model_dump(mode="json")
    settings_data[_WAREHOUSE_SETTINGS_SECTION] = warehouse_data
    return settings_data


async def _load_warehouse_mission_defaults(db: AsyncSession) -> WarehouseMissionDefaults:
    row = (await db.execute(select(SettingsRow).where(SettingsRow.id == 1))).scalar_one_or_none()
    return _extract_warehouse_mission_defaults(row.data if row else {})


async def _save_warehouse_mission_defaults(db: AsyncSession, defaults: WarehouseMissionDefaults) -> WarehouseMissionDefaults:
    row = (await db.execute(select(SettingsRow).where(SettingsRow.id == 1))).scalar_one_or_none()
    data = _with_warehouse_mission_defaults(row.data if row else {}, defaults)
    stmt = (
        pg_insert(SettingsRow)
        .values(id=1, data=data)
        .on_conflict_do_update(index_elements=[SettingsRow.id], set_={"data": data})
    )
    await db.execute(stmt)
    await db.commit()
    return defaults


async def _get_owned_warehouse_map(
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        owner_id: int,
) -> WarehouseMap:
    warehouse_map = await repo.get_owned_warehouse_map(
        db,
        warehouse_map_id=warehouse_map_id,
        owner_id=owner_id,
    )
    if warehouse_map is None:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    return warehouse_map


def _dock_out(dock) -> WarehouseDockOut:
    def _pose(j: dict) -> WarehouseDockLocalPose:
        return WarehouseDockLocalPose(
            x_m=float(j.get("x_m", 0)),
            y_m=float(j.get("y_m", 0)),
            z_m=float(j.get("z_m", 0)),
            yaw_deg=j.get("yaw_deg"),
        )
    return WarehouseDockOut(
        id=int(dock.id),
        name=dock.name,
        marker_id=dock.marker_id,
        charger_type=dock.charger_type,
        pose=_pose(dock.pose_local_json),
        entry_pose=_pose(dock.entry_pose_local_json),
        exit_pose=_pose(dock.exit_pose_local_json),
        active=bool(dock.active),
        created_at=dock.created_at,
    )


def _dock_config_from_station(dock) -> WarehouseDockConfig:
    def _pt(j: dict) -> WarehouseLocalPoint:
        return WarehouseLocalPoint(
            x_m=float(j.get("x_m", 0)),
            y_m=float(j.get("y_m", 0)),
            z_m=float(j.get("z_m", 0)),
            yaw_deg=j.get("yaw_deg"),
        )
    return WarehouseDockConfig(
        dock_pose=_pt(dock.pose_local_json),
        entry_pose=_pt(dock.entry_pose_local_json),
        exit_pose=_pt(dock.exit_pose_local_json),
        marker_id=dock.marker_id,
        dock_yaw_deg=dock.pose_local_json.get("yaw_deg"),
        precision_required=bool(dock.meta_data.get("precision_required", True)),
    )


# ------------------------------------------------------------------ mission defaults

@router.get("/mission-defaults", response_model=WarehouseMissionDefaults)
async def get_warehouse_mission_defaults(
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_user),
) -> WarehouseMissionDefaults:
    return await _load_warehouse_mission_defaults(db)


@router.put("/mission-defaults", response_model=WarehouseMissionDefaults)
async def update_warehouse_mission_defaults(
        payload: WarehouseMissionDefaults,
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_user),
) -> WarehouseMissionDefaults:
    return await _save_warehouse_mission_defaults(db, payload)


# ------------------------------------------------------------------ warehouse maps

@router.get("/maps", response_model=List[WarehouseMapOut])
async def list_warehouse_maps(
        limit: int = Query(default=100, ge=1, le=500),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> List[WarehouseMapOut]:
    maps = await repo.list_warehouse_maps(db, owner_id=int(user.id), limit=limit)
    return [
        WarehouseMapOut(
            id=int(m.id),
            name=m.name,
            area_m2=m.area_m2,
            created_at=m.created_at,
            polygon_local_m=repo.polygon_from_local(m),
        )
        for m in maps
    ]


@router.post("/maps", response_model=WarehouseMapOut, status_code=201)
async def create_warehouse_map(
        payload: WarehouseMapCreateIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> WarehouseMapOut:
    try:
        polygon_local_m = [tuple(pt) for pt in payload.polygon_local_m]
        warehouse_map = await repo.create_warehouse_map(
            db,
            owner_id=int(user.id),
            warehouse_name=payload.name,
            polygon_local_m=polygon_local_m,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    return WarehouseMapOut(
        id=int(warehouse_map.id),
        name=warehouse_map.name,
        area_m2=warehouse_map.area_m2,
        created_at=warehouse_map.created_at,
        polygon_local_m=repo.polygon_from_local(warehouse_map),
    )


@router.get("/maps/{warehouse_map_id}", response_model=WarehouseMapOut)
async def get_warehouse_map(
        warehouse_map_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> WarehouseMapOut:
    warehouse_map = await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, owner_id=int(user.id))
    return WarehouseMapOut(
        id=int(warehouse_map.id),
        name=warehouse_map.name,
        area_m2=warehouse_map.area_m2,
        created_at=warehouse_map.created_at,
        polygon_local_m=repo.polygon_from_local(warehouse_map),
    )


@router.delete("/maps/{warehouse_map_id}", status_code=204)
async def delete_warehouse_map(
        warehouse_map_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> None:
    deleted = await repo.delete_warehouse_map(
        db, warehouse_map_id=warehouse_map_id, owner_id=int(user.id)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    await db.commit()


# ------------------------------------------------------------------ dock stations

@router.get("/maps/{warehouse_map_id}/docks", response_model=List[WarehouseDockOut])
async def list_dock_stations(
        warehouse_map_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> List[WarehouseDockOut]:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, owner_id=int(user.id))
    docks = await repo.list_dock_stations(db, warehouse_map_id=warehouse_map_id)
    return [_dock_out(d) for d in docks]


@router.post("/maps/{warehouse_map_id}/docks", response_model=WarehouseDockOut, status_code=201)
async def create_dock_station(
        warehouse_map_id: int,
        payload: WarehouseDockCreateIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> WarehouseDockOut:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, owner_id=int(user.id))
    try:
        dock = await repo.create_dock_station(
            db,
            warehouse_map_id=warehouse_map_id,
            name=payload.name,
            pose_local_json=payload.pose.model_dump(),
            entry_pose_local_json=payload.entry_pose.model_dump(),
            exit_pose_local_json=payload.exit_pose.model_dump(),
            marker_id=payload.marker_id,
            charger_type=payload.charger_type,
            meta_data={"precision_required": payload.precision_required},
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    return _dock_out(dock)


@router.delete("/maps/{warehouse_map_id}/docks/{dock_id}", status_code=204)
async def delete_dock_station(
        warehouse_map_id: int,
        dock_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> None:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, owner_id=int(user.id))
    deactivated = await repo.deactivate_dock_station(
        db, dock_id=dock_id, warehouse_map_id=warehouse_map_id
    )
    if not deactivated:
        raise HTTPException(status_code=404, detail="Dock station not found")
    await db.commit()


# ------------------------------------------------------------------ mission

@router.post("/missions/start", response_model=WarehouseMissionLaunchOut)
async def start_warehouse_scan(
        payload: WarehouseScanStartIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> WarehouseMissionLaunchOut:
    warehouse_map = await _get_owned_warehouse_map(
        db,
        warehouse_map_id=int(payload.warehouse_map_id),
        owner_id=int(user.id),
    )
    mission_defaults = merge_warehouse_mission_defaults(
        await _load_warehouse_mission_defaults(db),
        payload.model_dump(
            exclude={"warehouse_map_id", "mission_name", "reference_mapping_job_id"},
            exclude_unset=True,
        ),
    )
    polygon_local_m = repo.polygon_from_local(warehouse_map)

    # Use registered dock station if one exists for this map
    dock_config: Optional[WarehouseDockConfig] = None
    docks = await repo.list_dock_stations(db, warehouse_map_id=int(warehouse_map.id))
    if docks:
        dock_config = _dock_config_from_station(docks[0])

    mission_payload = routes_flights.MissionCreateIn(
        name=payload.mission_name.strip(),
        # cruise_alt field on MissionCreateIn is used by the orchestrator as the
        # takeoff/hover height; for indoor missions it equals base_height_m (first scan layer).
        cruise_alt=float(mission_defaults.cruise_alt),
        mission_type=MissionType.WAREHOUSE_SCAN,
        warehouse_scan=WarehouseScanMissionParams(
            polygon_local_m=polygon_local_m,
            warehouse_map_id=int(warehouse_map.id),
            warehouse_name=warehouse_map.name,
            reference_mapping_job_id=payload.reference_mapping_job_id,
            dock_config=(
                WarehouseDockConfigParams(
                    dock_pose=WarehouseDockPoseParams(
                        x_m=float(dock_config.dock_pose.x_m),
                        y_m=float(dock_config.dock_pose.y_m),
                        z_m=float(dock_config.dock_pose.z_m),
                        yaw_deg=dock_config.dock_pose.yaw_deg,
                    ),
                    entry_pose=WarehouseDockPoseParams(
                        x_m=float(dock_config.entry_pose.x_m),
                        y_m=float(dock_config.entry_pose.y_m),
                        z_m=float(dock_config.entry_pose.z_m),
                        yaw_deg=dock_config.entry_pose.yaw_deg,
                    ),
                    exit_pose=WarehouseDockPoseParams(
                        x_m=float(dock_config.exit_pose.x_m),
                        y_m=float(dock_config.exit_pose.y_m),
                        z_m=float(dock_config.exit_pose.z_m),
                        yaw_deg=dock_config.exit_pose.yaw_deg,
                    ),
                    marker_id=dock_config.marker_id,
                    dock_yaw_deg=dock_config.dock_yaw_deg,
                    precision_required=bool(dock_config.precision_required),
                )
                if dock_config is not None
                else None
            ),
            corridor_spacing_m=float(mission_defaults.corridor_spacing_m),
            aisle_axis_deg=mission_defaults.aisle_axis_deg,
            clearance_m=float(mission_defaults.clearance_m),
            perimeter_offset_m=float(mission_defaults.perimeter_offset_m),
            scan_pattern=mission_defaults.scan_pattern,
            lane_strategy=mission_defaults.lane_strategy,
            view_mode=mission_defaults.view_mode,
            layer_count=int(mission_defaults.layer_count),
            layer_spacing_m=float(mission_defaults.layer_spacing_m),
            ceiling_height_m=float(mission_defaults.ceiling_height_m),
            ceiling_margin_m=float(mission_defaults.ceiling_margin_m),
            work_speed_mps=float(mission_defaults.work_speed_mps),
            transit_speed_mps=float(mission_defaults.transit_speed_mps),
            scan_pause_s=float(mission_defaults.scan_pause_s),
            interpolate_steps_work_leg=int(mission_defaults.interpolate_steps_work_leg),
            interpolate_steps_transit_leg=int(mission_defaults.interpolate_steps_transit_leg),
        ),
    )

    preflight = await routes_flights.run_preflight(mission_payload, user=user)
    if not preflight.can_start_mission:
        raise HTTPException(
            status_code=412,
            detail=(
                f"Warehouse preflight {preflight.overall_status}. "
                "Mission start blocked."
            ),
        )

    mission_payload.preflight_run_id = preflight.preflight_run_id
    mission = await routes_flights.create_mission(mission_payload, user=user)
    return WarehouseMissionLaunchOut(
        warehouse_map_id=int(warehouse_map.id),
        warehouse_name=warehouse_map.name,
        preflight=preflight,
        mission=mission,
    )


# ------------------------------------------------------------------ scanned maps

@router.get("/scanned-maps", response_model=List[WarehouseScannedMapOut])
async def list_scanned_maps(
        warehouse_map_id: Optional[int] = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=200),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> List[WarehouseScannedMapOut]:
    rows = await repo.list_ready_scanned_maps(
        db,
        owner_id=int(user.id),
        warehouse_map_id=warehouse_map_id,
        limit=limit,
    )
    if not rows:
        return []

    model_ids = [int(model.id) for _job, _warehouse_map, model in rows]
    asset_rows = await repo.list_assets_for_models(db, model_ids=model_ids)
    assets_by_model: dict[int, list[WarehouseAsset]] = {}
    for asset in asset_rows:
        assets_by_model.setdefault(int(asset.model_id), []).append(asset)

    results: list[WarehouseScannedMapOut] = []
    for job, warehouse_map, model in rows:
        assets = assets_by_model.get(int(model.id), [])
        if not any(asset.type == "TILESET_3D" for asset in assets):
            continue
        results.append(
            WarehouseScannedMapOut(
                job_id=int(job.id),
                model_id=int(model.id),
                model_version=int(model.version),
                warehouse_map_id=int(warehouse_map.id),
                warehouse_name=warehouse_map.name,
                status=job.status,
                created_at=job.created_at,
                finished_at=job.finished_at,
                polygon_local_m=repo.polygon_from_local(warehouse_map),
                assets=[
                    WarehouseScannedMapAssetOut(
                        id=int(asset.id),
                        type=asset.type,
                        url=asset.url,
                        created_at=asset.created_at,
                        meta_data=asset.meta_data if isinstance(asset.meta_data, dict) else {},
                    )
                    for asset in assets
                ],
            )
        )
    return results


@router.get("/scanned-maps/{job_id}", response_model=WarehouseScannedMapOut)
async def get_scanned_map(
        job_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_user),
) -> WarehouseScannedMapOut:
    """Fetch a single scanned map job by its job_id."""
    rows = await repo.list_ready_scanned_maps(
        db,
        owner_id=int(user.id),
        limit=200,
    )
    for job, warehouse_map, model in rows:
        if int(job.id) != job_id:
            continue
        asset_rows = await repo.list_assets_for_models(db, model_ids=[int(model.id)])
        if not any(a.type == "TILESET_3D" for a in asset_rows):
            raise HTTPException(status_code=404, detail="Scanned map has no 3D tileset yet")
        return WarehouseScannedMapOut(
            job_id=int(job.id),
            model_id=int(model.id),
            model_version=int(model.version),
            warehouse_map_id=int(warehouse_map.id),
            warehouse_name=warehouse_map.name,
            status=job.status,
            created_at=job.created_at,
            finished_at=job.finished_at,
            polygon_local_m=repo.polygon_from_local(warehouse_map),
            assets=[
                WarehouseScannedMapAssetOut(
                    id=int(a.id),
                    type=a.type,
                    url=a.url,
                    created_at=a.created_at,
                    meta_data=a.meta_data if isinstance(a.meta_data, dict) else {},
                )
                for a in asset_rows
            ],
        )
    raise HTTPException(status_code=404, detail="Scanned map not found")
