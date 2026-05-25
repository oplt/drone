from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseMap,
)


class WarehouseRepositoryError(RuntimeError):
    pass


@dataclass
class WarehouseModelVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime


class WarehouseMapMixin:
    async def get_owned_warehouse_map(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
    ) -> WarehouseMap | None:
        scope = (
            or_(WarehouseMap.owner_id == owner_id, WarehouseMap.org_id == org_id)
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == owner_id
        )
        return (
            await db.execute(select(WarehouseMap).where(WarehouseMap.id == warehouse_map_id, scope))
        ).scalar_one_or_none()

    async def list_warehouse_maps(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
        limit: int = 100,
    ) -> list[WarehouseMap]:
        scope = (
            or_(WarehouseMap.owner_id == owner_id, WarehouseMap.org_id == org_id)
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == owner_id
        )
        return (
            (
                await db.execute(
                    select(WarehouseMap).where(scope).order_by(WarehouseMap.id.desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def delete_warehouse_map(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
    ) -> bool:
        """Returns True if a row was deleted, False if not found / not owned."""
        warehouse_map = await self.get_owned_warehouse_map(
            db,
            warehouse_map_id=warehouse_map_id,
            owner_id=owner_id,
            org_id=org_id,
            allow_org_access=allow_org_access,
        )
        if warehouse_map is None:
            return False
        await db.delete(warehouse_map)
        return True

    async def create_warehouse_map(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None,
        project_id: int | None,
        warehouse_name: str,
        polygon_local_m: list[tuple[float, float]],
        meta_data: dict[str, Any] | None = None,
    ) -> WarehouseMap:
        """Create a warehouse map defined by a local metric polygon (no GPS)."""
        if len(polygon_local_m) < 3:
            raise WarehouseRepositoryError("Warehouse polygon requires at least 3 points.")
        # Compute area from the local polygon directly (metres²)
        from shapely.geometry import Polygon as _Polygon

        try:
            area_m2 = float(_Polygon(polygon_local_m).area)
        except Exception:
            area_m2 = None

        base_meta = dict(meta_data or {})
        base_meta["polygon_local_m"] = [[float(x), float(y)] for x, y in polygon_local_m]

        warehouse_map = WarehouseMap(
            owner_id=owner_id,
            org_id=org_id,
            project_id=project_id,
            name=warehouse_name.strip(),
            boundary=None,  # indoor — no GPS boundary
            centroid=None,
            area_m2=area_m2,
            meta_data=base_meta,
        )
        db.add(warehouse_map)
        await db.flush()
        return warehouse_map

    async def get_or_create_warehouse_map(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None,
        project_id: int | None,
        warehouse_map_id: int | None,
        warehouse_name: str | None,
        polygon_local_m: list[tuple[float, float]],
        meta_data: dict[str, Any] | None = None,
    ) -> WarehouseMap:
        if warehouse_map_id is not None:
            warehouse_map = await self.get_owned_warehouse_map(
                db,
                warehouse_map_id=int(warehouse_map_id),
                owner_id=owner_id,
                org_id=org_id,
                allow_org_access=org_id is not None,
            )
            if warehouse_map is None:
                raise WarehouseRepositoryError("Selected warehouse map was not found.")
            return warehouse_map
        resolved_name = (warehouse_name or "").strip() or self.auto_warehouse_name()
        return await self.create_warehouse_map(
            db,
            owner_id=owner_id,
            org_id=org_id,
            project_id=project_id,
            warehouse_name=resolved_name,
            polygon_local_m=polygon_local_m,
            meta_data=meta_data,
        )

    @staticmethod
    def auto_warehouse_name() -> str:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"Warehouse map {stamp}"

    @staticmethod
    def polygon_from_local(warehouse_map: WarehouseMap) -> list[list[float]]:
        """Return the local polygon [[x_m, y_m], ...] stored in meta_data."""
        meta = warehouse_map.meta_data if isinstance(warehouse_map.meta_data, dict) else {}
        raw = meta.get("polygon_local_m")
        if isinstance(raw, list):
            return [[float(pt[0]), float(pt[1])] for pt in raw if len(pt) >= 2]
        return []
