from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseMap
from backend.modules.warehouse.repository.contracts import WarehouseRepositoryError
from backend.modules.warehouse.repository.query_values import clamp_list_limit


def _normalize_polygon_local(
    polygon_local_m: list[tuple[float, float]] | list[list[float]],
) -> list[tuple[float, float]]:
    if not isinstance(polygon_local_m, list) or len(polygon_local_m) < 3:
        raise WarehouseRepositoryError("Warehouse polygon requires at least 3 points.")

    normalized: list[tuple[float, float]] = []
    for index, point in enumerate(polygon_local_m):
        try:
            if len(point) < 2:  # type: ignore[arg-type]
                raise ValueError
            x = float(point[0])  # type: ignore[index]
            y = float(point[1])  # type: ignore[index]
        except (TypeError, ValueError, IndexError):
            raise WarehouseRepositoryError(
                f"Warehouse polygon point {index} must be [x_m, y_m]."
            ) from None
        if not (math.isfinite(x) and math.isfinite(y)):
            raise WarehouseRepositoryError(
                f"Warehouse polygon point {index} must contain finite coordinates."
            )
        normalized.append((x, y))

    distinct = set(normalized[:-1] if normalized[0] == normalized[-1] else normalized)
    if len(distinct) < 3:
        raise WarehouseRepositoryError("Warehouse polygon requires at least 3 distinct points.")
    return normalized


def _polygon_area_m2(polygon_local_m: list[tuple[float, float]]) -> float:
    from shapely.geometry import Polygon as _Polygon

    polygon = _Polygon(polygon_local_m)
    if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
        raise WarehouseRepositoryError("Warehouse polygon is invalid or has zero area.")
    return float(polygon.area)


def _scope_for_owner(
    *,
    owner_id: int,
    org_id: int | None,
    allow_org_access: bool,
):
    return (
        or_(WarehouseMap.owner_id == int(owner_id), WarehouseMap.org_id == int(org_id))
        if allow_org_access and org_id is not None
        else WarehouseMap.owner_id == int(owner_id)
    )


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
        scope = _scope_for_owner(
            owner_id=owner_id,
            org_id=org_id,
            allow_org_access=allow_org_access,
        )
        return (
            await db.execute(
                select(WarehouseMap).where(WarehouseMap.id == int(warehouse_map_id), scope)
            )
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
        scope = _scope_for_owner(
            owner_id=owner_id,
            org_id=org_id,
            allow_org_access=allow_org_access,
        )
        return list(
            (
                await db.execute(
                    select(WarehouseMap)
                    .where(scope)
                    .order_by(WarehouseMap.id.desc())
                    .limit(clamp_list_limit(limit, default=100))
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
            warehouse_map_id=int(warehouse_map_id),
            owner_id=int(owner_id),
            org_id=org_id,
            allow_org_access=allow_org_access,
        )
        if warehouse_map is None:
            return False
        await db.delete(warehouse_map)
        await db.flush()
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
        polygon = _normalize_polygon_local(polygon_local_m)
        area_m2 = _polygon_area_m2(polygon)
        name = str(warehouse_name or "").strip()
        if not name:
            raise WarehouseRepositoryError("Warehouse name cannot be empty.")

        base_meta = dict(meta_data or {})
        base_meta["polygon_local_m"] = [[float(x), float(y)] for x, y in polygon]

        warehouse_map = WarehouseMap(
            owner_id=int(owner_id),
            org_id=org_id,
            project_id=project_id,
            name=name,
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
        allow_org_access: bool = False,
    ) -> WarehouseMap:
        if warehouse_map_id is not None:
            warehouse_map = await self.get_owned_warehouse_map(
                db,
                warehouse_map_id=int(warehouse_map_id),
                owner_id=int(owner_id),
                org_id=org_id,
                allow_org_access=allow_org_access,
            )
            if warehouse_map is None:
                raise WarehouseRepositoryError("Selected warehouse map was not found.")
            return warehouse_map
        resolved_name = (warehouse_name or "").strip() or self.auto_warehouse_name()
        return await self.create_warehouse_map(
            db,
            owner_id=int(owner_id),
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
        if not isinstance(raw, list):
            return []
        points: list[list[float]] = []
        for point in raw:
            try:
                if len(point) < 2:  # type: ignore[arg-type]
                    continue
                x = float(point[0])  # type: ignore[index]
                y = float(point[1])  # type: ignore[index]
            except (TypeError, ValueError, IndexError):
                continue
            if math.isfinite(x) and math.isfinite(y):
                points.append([x, y])
        return points
