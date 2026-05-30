from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity.models import User
from backend.modules.organizations.service import can_access_org_scope, get_default_project
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseSensorRig,
)
from backend.modules.warehouse.planning.mission import WarehouseMissionDefaults
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.repository.settings import WarehouseSettingsRepository

_SETTINGS_SECTION = "warehouse"
_DEFAULTS_KEY = "mission_defaults"
_EXPLORATION_PROFILE_KEY = "exploration_profile"


class WarehouseApplication:
    def __init__(self) -> None:
        self.maps = WarehouseMappingRepository()
        self.settings = WarehouseSettingsRepository()

    async def get_map(
        self,
        db: AsyncSession,
        *,
        map_id: int,
        user: User,
    ) -> WarehouseMap | None:
        return await self.maps.get_owned_warehouse_map(
            db,
            warehouse_map_id=map_id,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
        )

    async def list_maps(self, db: AsyncSession, *, user: User, limit: int) -> list[WarehouseMap]:
        return await self.maps.list_warehouse_maps(
            db,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
            limit=limit,
        )

    async def list_docks(self, db: AsyncSession, *, map_id: int) -> list[WarehouseDockStation]:
        return await self.maps.list_dock_stations(db, warehouse_map_id=map_id)

    async def list_scanned_maps(
        self, db: AsyncSession, *, user: User, map_id: int | None, limit: int
    ) -> list[tuple[WarehouseMappingJob, WarehouseMap, WarehouseModel]]:
        return await self.maps.list_scanned_maps(
            db,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
            warehouse_map_id=map_id,
            limit=limit,
        )

    async def delete_scanned_map(
        self, db: AsyncSession, *, job_id: int, user: User
    ) -> bool:
        try:
            deleted = await self.maps.delete_scanned_map_by_job_id(
                db,
                job_id=job_id,
                owner_id=int(user.id),
                org_id=user.org_id,
                allow_org_access=can_access_org_scope(user),
            )
            if deleted:
                await db.commit()
            return deleted
        except Exception:
            await db.rollback()
            raise

    async def list_assets(self, db: AsyncSession, *, model_ids: list[int]) -> list[WarehouseAsset]:
        return await self.maps.list_assets_for_models(db, model_ids=model_ids)

    async def list_sensor_rigs(
        self, db: AsyncSession, *, user: User, limit: int
    ) -> list[WarehouseSensorRig]:
        return await self.maps.list_sensor_rigs(
            db,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
            limit=limit,
        )

    async def get_sensor_rig(
        self, db: AsyncSession, *, sensor_rig_id: int, user: User
    ) -> WarehouseSensorRig | None:
        return await self.maps.get_owned_sensor_rig(
            db,
            sensor_rig_id=sensor_rig_id,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
        )

    def polygon_from_local(self, warehouse_map: WarehouseMap) -> list[list[float]]:
        return self.maps.polygon_from_local(warehouse_map)

    async def load_mission_defaults(self, db: AsyncSession) -> dict[str, Any]:
        data = await self.settings.read_document(db)
        warehouse = data.get(_SETTINGS_SECTION)
        if not isinstance(warehouse, dict):
            return {}
        defaults = warehouse.get(_DEFAULTS_KEY)
        return defaults if isinstance(defaults, dict) else {}

    async def save_mission_defaults(
        self, db: AsyncSession, *, defaults: WarehouseMissionDefaults
    ) -> WarehouseMissionDefaults:
        data = await self.settings.read_document(db)
        warehouse = data.get(_SETTINGS_SECTION)
        section = dict(warehouse) if isinstance(warehouse, dict) else {}
        section[_DEFAULTS_KEY] = defaults.model_dump(mode="json")
        data[_SETTINGS_SECTION] = section
        await self.settings.write_document(db, data=data)
        return defaults

    async def load_exploration_profile(self, db: AsyncSession) -> dict[str, Any]:
        data = await self.settings.read_document(db)
        warehouse = data.get(_SETTINGS_SECTION)
        if not isinstance(warehouse, dict):
            return {}
        profile = warehouse.get(_EXPLORATION_PROFILE_KEY)
        return profile if isinstance(profile, dict) else {}

    async def save_exploration_profile(
        self, db: AsyncSession, *, profile: dict[str, Any]
    ) -> dict[str, Any]:
        data = await self.settings.read_document(db)
        warehouse = data.get(_SETTINGS_SECTION)
        section = dict(warehouse) if isinstance(warehouse, dict) else {}
        section[_EXPLORATION_PROFILE_KEY] = dict(profile)
        data[_SETTINGS_SECTION] = section
        await self.settings.write_document(db, data=data)
        return dict(profile)

    async def create_map(
        self,
        db: AsyncSession,
        *,
        user: User,
        name: str,
        polygon_local_m: list[tuple[float, float]],
    ) -> WarehouseMap:
        try:
            project = (
                await get_default_project(db, org_id=int(user.org_id)) if user.org_id else None
            )
            warehouse_map = await self.maps.create_warehouse_map(
                db,
                owner_id=int(user.id),
                org_id=user.org_id,
                project_id=project.id if project else None,
                warehouse_name=name,
                polygon_local_m=polygon_local_m,
            )
            await db.commit()
            return warehouse_map
        except Exception:
            await db.rollback()
            raise

    async def create_simulation_map(
        self,
        db: AsyncSession,
        *,
        user: User,
        name: str,
        polygon_local_m: list[tuple[float, float]],
        scenario_name: str,
    ) -> WarehouseMap:
        try:
            project = (
                await get_default_project(db, org_id=int(user.org_id)) if user.org_id else None
            )
            warehouse_map = await self.maps.create_warehouse_map(
                db,
                owner_id=int(user.id),
                org_id=user.org_id,
                project_id=project.id if project else None,
                warehouse_name=name,
                polygon_local_m=polygon_local_m,
                meta_data={"source": "simulation", "scenario_name": scenario_name},
            )
            await db.commit()
            return warehouse_map
        except Exception:
            await db.rollback()
            raise

    async def delete_map(self, db: AsyncSession, *, map_id: int, user: User) -> bool:
        deleted = await self.maps.delete_warehouse_map(
            db,
            warehouse_map_id=map_id,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
        )
        if deleted:
            await db.commit()
        return deleted

    async def create_dock(
        self, db: AsyncSession, *, map_id: int, payload: Any
    ) -> WarehouseDockStation:
        try:
            dock = await self.maps.create_dock_station(
                db,
                warehouse_map_id=map_id,
                name=payload.name,
                pose_local_json=payload.pose.model_dump(),
                entry_pose_local_json=payload.entry_pose.model_dump(),
                exit_pose_local_json=payload.exit_pose.model_dump(),
                marker_id=payload.marker_id,
                charger_type=payload.charger_type,
                meta_data={
                    "precision_required": payload.precision_required,
                    "marker_family": payload.marker_family,
                    "marker_size_m": payload.marker_size_m,
                    "marker_pose_covariance": list(payload.marker_pose_covariance or []),
                    "marker_visible": False,
                    "last_observed_at": None,
                },
            )
            await db.commit()
            return dock
        except Exception:
            await db.rollback()
            raise

    async def delete_dock(self, db: AsyncSession, *, map_id: int, dock_id: int) -> bool:
        deactivated = await self.maps.deactivate_dock_station(
            db, dock_id=dock_id, warehouse_map_id=map_id
        )
        if deactivated:
            await db.commit()
        return deactivated

    async def update_dock(
        self, db: AsyncSession, *, map_id: int, dock_id: int, payload: Any
    ) -> WarehouseDockStation | None:
        fields_set = getattr(payload, "model_fields_set", set())
        values: dict[str, Any] = {}
        if "name" in fields_set and payload.name is not None:
            values["name"] = payload.name.strip()
        for field_name, column_name in (
            ("pose", "pose_local_json"),
            ("entry_pose", "entry_pose_local_json"),
            ("exit_pose", "exit_pose_local_json"),
        ):
            pose = getattr(payload, field_name)
            if field_name in fields_set and pose is not None:
                values[column_name] = pose.model_dump()
        for field_name in ("marker_id", "charger_type"):
            if field_name in fields_set:
                values[field_name] = getattr(payload, field_name)
        meta_updates = {
            "precision_required": payload.precision_required,
            "marker_family": payload.marker_family,
            "marker_size_m": payload.marker_size_m,
            "marker_pose_covariance": payload.marker_pose_covariance,
        }
        meta_values = {key: value for key, value in meta_updates.items() if key in fields_set}
        if meta_values:
            current = next(
                (dock for dock in await self.list_docks(db, map_id=map_id) if dock.id == dock_id),
                None,
            )
            meta_data = dict(current.meta_data or {}) if current is not None else {}
            meta_data.update(meta_values)
            values["meta_data"] = meta_data
        updated = await self.maps.update_dock_station(
            db,
            dock_id=dock_id,
            warehouse_map_id=map_id,
            values=values,
        )
        if updated is not None:
            await db.commit()
        return updated

    async def create_sensor_rig(
        self,
        db: AsyncSession,
        *,
        user: User,
        payload: Any,
    ) -> WarehouseSensorRig:
        try:
            rig = await self.maps.create_sensor_rig(
                db,
                owner_id=int(user.id),
                org_id=user.org_id,
                name=payload.name,
                camera_model=payload.camera_model,
                stereo_baseline_m=payload.stereo_baseline_m,
                intrinsics_url=payload.intrinsics_url,
                extrinsics_url=payload.extrinsics_url,
                imu_transform_json=payload.imu_transform_json,
                firmware_version=payload.firmware_version,
                isaac_ros_version=payload.isaac_ros_version,
            )
            await db.commit()
            return rig
        except Exception:
            await db.rollback()
            raise

    async def update_sensor_rig_calibration(
        self,
        db: AsyncSession,
        *,
        rig: WarehouseSensorRig,
        payload: Any,
    ) -> WarehouseSensorRig:
        try:
            updated = await self.maps.update_sensor_rig_calibration(
                db,
                rig=rig,
                calibration_status=payload.calibration_status,
                calibration_hash=payload.calibration_hash,
                intrinsics_url=payload.intrinsics_url,
                extrinsics_url=payload.extrinsics_url,
                imu_transform_json=payload.imu_transform_json,
                calibration_meta=payload.calibration_meta,
            )
            await db.commit()
            return updated
        except Exception:
            await db.rollback()
            raise

    async def delete_sensor_rig(
        self, db: AsyncSession, *, rig: WarehouseSensorRig
    ) -> None:
        await self.maps.deactivate_sensor_rig(db, rig=rig)
        await db.commit()


warehouse_application = WarehouseApplication()
