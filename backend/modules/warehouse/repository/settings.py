from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.settings.models import SettingsRow


class WarehouseSettingsRepository:
    async def read_document(self, db: AsyncSession) -> dict[str, Any]:
        row = await db.scalar(select(SettingsRow).where(SettingsRow.id == 1))
        return dict(row.data) if row and isinstance(row.data, dict) else {}

    async def write_document(self, db: AsyncSession, *, data: dict[str, Any]) -> None:
        stmt = (
            pg_insert(SettingsRow)
            .values(id=1, data=data)
            .on_conflict_do_update(index_elements=[SettingsRow.id], set_={"data": data})
        )
        await db.execute(stmt)
        await db.commit()
