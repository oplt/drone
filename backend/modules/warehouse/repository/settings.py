from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.settings.models import SettingsRow


class WarehouseSettingsRepository:
    async def read_document(self, db: AsyncSession) -> dict[str, Any]:
        row = await db.scalar(select(SettingsRow).where(SettingsRow.id == 1))
        if not row or not isinstance(row.data, dict):
            return {}
        # Return an isolated document so callers cannot accidentally mutate an
        # ORM-loaded JSON object outside an explicit write path.
        return deepcopy(dict(row.data))

    async def write_document(
        self,
        db: AsyncSession,
        *,
        data: Mapping[str, Any],
        commit: bool = True,
    ) -> None:
        if not isinstance(data, Mapping):
            raise TypeError("settings data must be a mapping")
        payload = deepcopy(dict(data))
        stmt = (
            pg_insert(SettingsRow)
            .values(id=1, data=payload)
            .on_conflict_do_update(index_elements=[SettingsRow.id], set_={"data": payload})
        )
        await db.execute(stmt)
        if commit:
            await db.commit()
        else:
            await db.flush()
