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
)
from backend.modules.warehouse.planning.mission import WarehouseMissionDefaults
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.repository.settings import WarehouseSettingsRepository

_SETTINGS_SECTION = "warehouse"
_DEFAULTS_KEY = "mission_defaults"


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
        return await self.maps.list_ready_scanned_maps(
            db,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
            warehouse_map_id=map_id,
            limit=limit,
        )

    async def list_assets(self, db: AsyncSession, *, model_ids: list[int]) -> list[WarehouseAsset]:
        return await self.maps.list_assets_for_models(db, model_ids=model_ids)

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
                meta_data={"precision_required": payload.precision_required},
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


warehouse_application = WarehouseApplication()
