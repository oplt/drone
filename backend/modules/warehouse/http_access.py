from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.organizations.service import can_access_org_scope
from backend.modules.warehouse.models import WarehouseMap
from backend.modules.warehouse.repository import WarehouseMappingRepository
from backend.modules.warehouse.repository.settings import WarehouseSettingsRepository

repo = WarehouseMappingRepository()
settings_repo = WarehouseSettingsRepository()
SETTINGS_SECTION = "warehouse"
MISSION_DEFAULTS_KEY = "mission_defaults"
EXPLORATION_PROFILE_KEY = "exploration_profile"


async def get_map_or_404(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    user: Any,
) -> WarehouseMap:
    warehouse_map = await repo.get_owned_warehouse_map(
        db,
        warehouse_map_id=warehouse_map_id,
        owner_id=int(user.id),
        org_id=user.org_id,
        allow_org_access=can_access_org_scope(user),
    )
    if warehouse_map is None:
        raise HTTPException(status_code=404, detail="Warehouse map not found")
    return warehouse_map


async def read_warehouse_settings(db: AsyncSession) -> dict[str, Any]:
    data = await settings_repo.read_document(db)
    section = data.get(SETTINGS_SECTION)
    return dict(section) if isinstance(section, dict) else {}


async def write_warehouse_setting(
    db: AsyncSession,
    *,
    key: str,
    value: dict[str, Any],
) -> None:
    data = await settings_repo.read_document(db)
    section = data.get(SETTINGS_SECTION)
    warehouse = dict(section) if isinstance(section, dict) else {}
    warehouse[key] = value
    data[SETTINGS_SECTION] = warehouse
    await settings_repo.write_document(db, data=data)
