from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseDockStation,
)


class WarehouseRepositoryError(RuntimeError):
    pass


@dataclass
class WarehouseModelVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime


class WarehouseDockMixin:
    async def list_dock_stations(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
    ) -> list[WarehouseDockStation]:
        return (
            (
                await db.execute(
                    select(WarehouseDockStation)
                    .where(
                        WarehouseDockStation.warehouse_map_id == warehouse_map_id,
                        WarehouseDockStation.active.is_(True),
                    )
                    .order_by(WarehouseDockStation.id.asc())
                )
            )
            .scalars()
            .all()
        )

    async def create_dock_station(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        name: str,
        pose_local_json: dict[str, Any],
        entry_pose_local_json: dict[str, Any],
        exit_pose_local_json: dict[str, Any],
        marker_id: str | None = None,
        charger_type: str | None = None,
        meta_data: dict[str, Any] | None = None,
    ) -> WarehouseDockStation:
        dock = WarehouseDockStation(
            warehouse_map_id=warehouse_map_id,
            name=name.strip(),
            marker_id=marker_id,
            charger_type=charger_type,
            pose_local_json=dict(pose_local_json),
            entry_pose_local_json=dict(entry_pose_local_json),
            exit_pose_local_json=dict(exit_pose_local_json),
            meta_data=dict(meta_data or {}),
            active=True,
        )
        db.add(dock)
        await db.flush()
        return dock

    async def deactivate_dock_station(
        self,
        db: AsyncSession,
        *,
        dock_id: int,
        warehouse_map_id: int,
    ) -> bool:
        dock = (
            await db.execute(
                select(WarehouseDockStation).where(
                    WarehouseDockStation.id == dock_id,
                    WarehouseDockStation.warehouse_map_id == warehouse_map_id,
                )
            )
        ).scalar_one_or_none()
        if dock is None:
            return False
        dock.active = False
        return True

    async def update_dock_station(
        self,
        db: AsyncSession,
        *,
        dock_id: int,
        warehouse_map_id: int,
        values: dict[str, Any],
    ) -> WarehouseDockStation | None:
        dock = (
            await db.execute(
                select(WarehouseDockStation).where(
                    WarehouseDockStation.id == dock_id,
                    WarehouseDockStation.warehouse_map_id == warehouse_map_id,
                    WarehouseDockStation.active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if dock is None:
            return None
        for key, value in values.items():
            setattr(dock, key, value)
        await db.flush()
        return dock
