from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import (
    OrgUser,
    require_mission_exec,
    require_org_user,
    require_org_write,
)
from backend.modules.missions.api import routes as routes_flights
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.warehouse.application import warehouse_application
from backend.modules.warehouse.models import WarehouseAsset, WarehouseMap
from backend.modules.warehouse.planning.exploration import (
    WarehouseExplorationMissionParams,
)
from backend.modules.warehouse.planning.local_planner import (
    WarehouseDockConfig,
    WarehouseLocalPoint,
)
from backend.modules.warehouse.planning.mission import (
    WarehouseDockConfigParams,
    WarehouseDockPoseParams,
    WarehouseMissionDefaults,
    WarehouseMissionDefaultsPatch,
    WarehouseScanMissionParams,
    merge_warehouse_mission_defaults,
)

router = APIRouter(prefix="/warehouse", tags=["warehouse"])
logger = logging.getLogger(__name__)
_WAREHOUSE_SETTINGS_SECTION = "warehouse"
_WAREHOUSE_MISSION_DEFAULTS_KEY = "mission_defaults"

# ------------------------------------------------------------------ schemas


class WarehouseScanStartIn(WarehouseMissionDefaultsPatch):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = Field(default="Warehouse Scan", min_length=1, max_length=120)
    reference_mapping_job_id: int | None = Field(default=None, ge=1)


class WarehouseExplorationStartIn(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = Field(default="Warehouse Exploration", min_length=1, max_length=120)
    hover_alt_m: float = Field(default=2.5, gt=0.2, le=20.0)
    dock_id: int | None = Field(default=None, ge=1)
    exploration: WarehouseExplorationMissionParams = Field(
        default_factory=WarehouseExplorationMissionParams,
    )


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
    meta_data: dict[str, Any] = Field(default_factory=dict)


class WarehouseScannedMapOut(BaseModel):
    job_id: int
    model_id: int
    model_version: int
    warehouse_map_id: int
    warehouse_name: str
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    polygon_local_m: list[list[float]] = Field(default_factory=list)
    assets: list[WarehouseScannedMapAssetOut] = Field(default_factory=list)


class WarehouseMapCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    # Option A – simple rectangle: supply width and length in metres
    width_m: float | None = Field(default=None, gt=0.0, le=500.0)
    length_m: float | None = Field(default=None, gt=0.0, le=500.0)
    # Option B – explicit polygon in the local metric frame [[x_m, y_m], ...]
    polygon_local_m: list[list[float]] | None = Field(default=None, min_length=3)

    @model_validator(mode="after")
    def _resolve_polygon(self) -> WarehouseMapCreateIn:
        if self.polygon_local_m is not None:
            return self
        if self.width_m is not None and self.length_m is not None:
            w, l = float(self.width_m), float(self.length_m)
            self.polygon_local_m = [[0.0, 0.0], [w, 0.0], [w, l], [0.0, l]]
            return self
        raise ValueError("Supply either polygon_local_m, or both width_m and length_m.")


class WarehouseMapOut(BaseModel):
    id: int
    name: str
    area_m2: float | None
    created_at: datetime
    polygon_local_m: list[list[float]] = Field(default_factory=list)


class WarehouseDockLocalPose(BaseModel):
    x_m: float
    y_m: float
    z_m: float
    yaw_deg: float | None = None


class WarehouseDockCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    pose: WarehouseDockLocalPose
    entry_pose: WarehouseDockLocalPose
    exit_pose: WarehouseDockLocalPose
    marker_id: str | None = Field(default=None, max_length=128)
    charger_type: str | None = Field(default=None, max_length=64)
    precision_required: bool = True


class WarehouseDockOut(BaseModel):
    id: int
    name: str
    marker_id: str | None
    charger_type: str | None
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
        logger.warning(
            "Invalid stored warehouse mission defaults. Falling back to built-in values."
        )
        return WarehouseMissionDefaults()


async def _get_owned_warehouse_map(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    user,
) -> WarehouseMap:
    warehouse_map = await warehouse_application.get_map(db, map_id=warehouse_map_id, user=user)
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


def _dock_config_params(
    dock_config: WarehouseDockConfig | None,
) -> WarehouseDockConfigParams | None:
    if dock_config is None:
        return None
    return WarehouseDockConfigParams(
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


# ------------------------------------------------------------------ mission defaults


@router.get("/mission-defaults", response_model=WarehouseMissionDefaults)
async def get_warehouse_mission_defaults(
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMissionDefaults:
    return _extract_warehouse_mission_defaults(
        await warehouse_application.load_mission_defaults(db)
    )


@router.put("/mission-defaults", response_model=WarehouseMissionDefaults)
async def update_warehouse_mission_defaults(
    payload: WarehouseMissionDefaults,
    db: AsyncSession = Depends(get_db),
    _org_user: OrgUser = Depends(require_org_write),
) -> WarehouseMissionDefaults:
    return await warehouse_application.save_mission_defaults(db, defaults=payload)


# ------------------------------------------------------------------ warehouse maps


@router.get("/maps", response_model=list[WarehouseMapOut])
async def list_warehouse_maps(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseMapOut]:
    user = org_user.user
    maps = await warehouse_application.list_maps(db, user=user, limit=limit)
    return [
        WarehouseMapOut(
            id=int(m.id),
            name=m.name,
            area_m2=m.area_m2,
            created_at=m.created_at,
            polygon_local_m=warehouse_application.polygon_from_local(m),
        )
        for m in maps
    ]


@router.post("/maps", response_model=WarehouseMapOut, status_code=201)
async def create_warehouse_map(
    payload: WarehouseMapCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseMapOut:
    user = org_user.user
    try:
        polygon_local_m = [tuple(pt) for pt in payload.polygon_local_m]
        warehouse_map = await warehouse_application.create_map(
            db,
            user=user,
            name=payload.name,
            polygon_local_m=polygon_local_m,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WarehouseMapOut(
        id=int(warehouse_map.id),
        name=warehouse_map.name,
        area_m2=warehouse_map.area_m2,
        created_at=warehouse_map.created_at,
        polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
    )


@router.get("/maps/{warehouse_map_id}", response_model=WarehouseMapOut)
async def get_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseMapOut:
    warehouse_map = await _get_owned_warehouse_map(
        db, warehouse_map_id=warehouse_map_id, user=org_user.user
    )
    return WarehouseMapOut(
        id=int(warehouse_map.id),
        name=warehouse_map.name,
        area_m2=warehouse_map.area_m2,
        created_at=warehouse_map.created_at,
        polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
    )


@router.delete("/maps/{warehouse_map_id}", status_code=204)
async def delete_warehouse_map(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    user = org_user.user
    deleted = await warehouse_application.delete_map(db, map_id=warehouse_map_id, user=user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse map not found")


# ------------------------------------------------------------------ dock stations


@router.get("/maps/{warehouse_map_id}/docks", response_model=list[WarehouseDockOut])
async def list_dock_stations(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseDockOut]:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    docks = await warehouse_application.list_docks(db, map_id=warehouse_map_id)
    return [_dock_out(d) for d in docks]


@router.post("/maps/{warehouse_map_id}/docks", response_model=WarehouseDockOut, status_code=201)
async def create_dock_station(
    warehouse_map_id: int,
    payload: WarehouseDockCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseDockOut:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    try:
        dock = await warehouse_application.create_dock(db, map_id=warehouse_map_id, payload=payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _dock_out(dock)


@router.delete("/maps/{warehouse_map_id}/docks/{dock_id}", status_code=204)
async def delete_dock_station(
    warehouse_map_id: int,
    dock_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    await _get_owned_warehouse_map(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    deactivated = await warehouse_application.delete_dock(
        db, map_id=warehouse_map_id, dock_id=dock_id
    )
    if not deactivated:
        raise HTTPException(status_code=404, detail="Dock station not found")


# ------------------------------------------------------------------ mission


@router.post("/missions/start", response_model=WarehouseMissionLaunchOut)
async def start_warehouse_scan(
    payload: WarehouseScanStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionLaunchOut:
    user = org_user.user
    warehouse_map = await _get_owned_warehouse_map(
        db,
        warehouse_map_id=int(payload.warehouse_map_id),
        user=user,
    )
    mission_defaults = merge_warehouse_mission_defaults(
        _extract_warehouse_mission_defaults(await warehouse_application.load_mission_defaults(db)),
        payload.model_dump(
            exclude={"warehouse_map_id", "mission_name", "reference_mapping_job_id"},
            exclude_unset=True,
        ),
    )
    polygon_local_m = warehouse_application.polygon_from_local(warehouse_map)

    # Use registered dock station if one exists for this map
    dock_config: WarehouseDockConfig | None = None
    docks = await warehouse_application.list_docks(db, map_id=int(warehouse_map.id))
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
            dock_config=_dock_config_params(dock_config),
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
            detail=(f"Warehouse preflight {preflight.overall_status}. Mission start blocked."),
        )

    mission_payload.preflight_run_id = preflight.preflight_run_id
    mission = await routes_flights.create_mission(mission_payload, user=user)
    return WarehouseMissionLaunchOut(
        warehouse_map_id=int(warehouse_map.id),
        warehouse_name=warehouse_map.name,
        preflight=preflight,
        mission=mission,
    )


@router.post("/missions/exploration/start", response_model=WarehouseMissionLaunchOut)
async def start_warehouse_exploration(
    payload: WarehouseExplorationStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseMissionLaunchOut:
    user = org_user.user
    warehouse_map = await _get_owned_warehouse_map(
        db,
        warehouse_map_id=int(payload.warehouse_map_id),
        user=user,
    )

    docks = await warehouse_application.list_docks(db, map_id=int(warehouse_map.id))
    selected_station = None
    if payload.dock_id is not None:
        for dock in docks:
            if int(dock.id) == int(payload.dock_id):
                selected_station = dock
                break
        if selected_station is None:
            raise HTTPException(status_code=404, detail="Requested dock station not found")
    elif docks:
        selected_station = docks[0]

    dock_config = payload.exploration.dock_config
    if dock_config is None and selected_station is not None:
        dock_config = _dock_config_params(_dock_config_from_station(selected_station))
    if dock_config is None:
        raise HTTPException(
            status_code=412,
            detail="Indoor warehouse exploration requires a registered dock station or explicit dock_config.",
        )

    exploration_payload = WarehouseExplorationMissionParams.model_validate(
        {
            **payload.exploration.model_dump(
                mode="python",
                exclude={"warehouse_map_id", "warehouse_name", "dock_config"},
            ),
            "warehouse_map_id": int(warehouse_map.id),
            "warehouse_name": warehouse_map.name,
            "dock_config": dock_config.model_dump(mode="python"),
        }
    )

    mission_payload = routes_flights.MissionCreateIn(
        name=payload.mission_name.strip(),
        cruise_alt=float(payload.hover_alt_m),
        mission_type=MissionType.INDOOR_EXPLORATION,
        warehouse_exploration=exploration_payload,
    )

    preflight = await routes_flights.run_preflight(mission_payload, user=user)
    if not preflight.can_start_mission:
        raise HTTPException(
            status_code=412,
            detail=(
                f"Warehouse exploration preflight {preflight.overall_status}. "
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


@router.get("/scanned-maps", response_model=list[WarehouseScannedMapOut])
async def list_scanned_maps(
    warehouse_map_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[WarehouseScannedMapOut]:
    user = org_user.user
    rows = await warehouse_application.list_scanned_maps(
        db, user=user, map_id=warehouse_map_id, limit=limit
    )
    if not rows:
        return []

    model_ids = [int(model.id) for _job, _warehouse_map, model in rows]
    asset_rows = await warehouse_application.list_assets(db, model_ids=model_ids)
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
                polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
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
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScannedMapOut:
    """Fetch a single scanned map job by its job_id."""
    rows = await warehouse_application.list_scanned_maps(
        db, user=org_user.user, map_id=None, limit=200
    )
    for job, warehouse_map, model in rows:
        if int(job.id) != job_id:
            continue
        asset_rows = await warehouse_application.list_assets(db, model_ids=[int(model.id)])
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
            polygon_local_m=warehouse_application.polygon_from_local(warehouse_map),
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
