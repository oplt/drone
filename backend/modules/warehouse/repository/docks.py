from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseDockStation


class WarehouseRepositoryError(RuntimeError):
    pass


@dataclass(slots=True)
class WarehouseModelVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime


_DOCK_UPDATE_FIELDS = frozenset(
    {
        "name",
        "marker_id",
        "charger_type",
        "pose_local_json",
        "entry_pose_local_json",
        "exit_pose_local_json",
        "meta_data",
        "active",
    }
)
_JSON_OBJECT_FIELDS = frozenset(
    {
        "pose_local_json",
        "entry_pose_local_json",
        "exit_pose_local_json",
        "meta_data",
    }
)
_OPTIONAL_STR_FIELDS = frozenset({"marker_id", "charger_type"})


def _clean_name(value: str, *, field_name: str = "name") -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise WarehouseRepositoryError(f"Dock {field_name} cannot be empty.")
    return cleaned


def _clean_optional_str(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _json_object(value: dict[str, Any] | None, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WarehouseRepositoryError(f"{field_name} must be a JSON object.")
    return dict(value)


def _normalize_dock_update_values(values: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise WarehouseRepositoryError("Dock update values must be a dictionary.")

    unknown = sorted(set(values) - _DOCK_UPDATE_FIELDS)
    if unknown:
        raise WarehouseRepositoryError(
            "Unsupported dock update field(s): " + ", ".join(unknown)
        )

    normalized: dict[str, Any] = {}
    for key, value in values.items():
        if key == "name":
            normalized[key] = _clean_name(str(value))
        elif key in _OPTIONAL_STR_FIELDS:
            normalized[key] = _clean_optional_str(value)
        elif key in _JSON_OBJECT_FIELDS:
            normalized[key] = _json_object(value, field_name=key)
        elif key == "active":
            normalized[key] = bool(value)
        else:
            normalized[key] = value
    return normalized


class WarehouseDockMixin:
    async def list_dock_stations(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
    ) -> list[WarehouseDockStation]:
        rows = await db.execute(
            select(WarehouseDockStation)
            .where(
                WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                WarehouseDockStation.active.is_(True),
            )
            .order_by(WarehouseDockStation.id.asc())
        )
        return list(rows.scalars().all())

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
            warehouse_map_id=int(warehouse_map_id),
            name=_clean_name(name),
            marker_id=_clean_optional_str(marker_id),
            charger_type=_clean_optional_str(charger_type),
            pose_local_json=_json_object(pose_local_json, field_name="pose_local_json"),
            entry_pose_local_json=_json_object(
                entry_pose_local_json, field_name="entry_pose_local_json"
            ),
            exit_pose_local_json=_json_object(
                exit_pose_local_json, field_name="exit_pose_local_json"
            ),
            meta_data=_json_object(meta_data, field_name="meta_data"),
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
        row = await db.execute(
            select(WarehouseDockStation).where(
                WarehouseDockStation.id == int(dock_id),
                WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                WarehouseDockStation.active.is_(True),
            )
        )
        dock = row.scalar_one_or_none()
        if dock is None:
            return False
        dock.active = False
        await db.flush()
        return True

    async def update_dock_station(
        self,
        db: AsyncSession,
        *,
        dock_id: int,
        warehouse_map_id: int,
        values: dict[str, Any],
    ) -> WarehouseDockStation | None:
        normalized = _normalize_dock_update_values(values)
        if not normalized:
            row = await db.execute(
                select(WarehouseDockStation).where(
                    WarehouseDockStation.id == int(dock_id),
                    WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                    WarehouseDockStation.active.is_(True),
                )
            )
            return row.scalar_one_or_none()

        row = await db.execute(
            select(WarehouseDockStation).where(
                WarehouseDockStation.id == int(dock_id),
                WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                WarehouseDockStation.active.is_(True),
            )
        )
        dock = row.scalar_one_or_none()
        if dock is None:
            return None
        for key, value in normalized.items():
            setattr(dock, key, value)
        await db.flush()
        return dock
