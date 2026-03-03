from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Field as FieldEntity
from backend.db.models import FieldModel


@dataclass
class FieldVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime


class FieldRegistryService:
    """
    Field registry helper:
    - validates field ownership
    - resolves next model version
    - lists model versions
    """

    async def get_owned_field(
        self,
        db: AsyncSession,
        *,
        field_id: int,
        owner_id: int,
    ) -> Optional[FieldEntity]:
        return (
            await db.execute(
                select(FieldEntity).where(
                    FieldEntity.id == field_id,
                    FieldEntity.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()

    async def next_model_version(self, db: AsyncSession, *, field_id: int) -> int:
        max_version = (
            await db.execute(
                select(func.max(FieldModel.version)).where(FieldModel.field_id == field_id)
            )
        ).scalar_one()
        return int(max_version or 0) + 1

    async def list_versions(
        self,
        db: AsyncSession,
        *,
        field_id: int,
    ) -> List[FieldVersionEntry]:
        models = (
            await db.execute(
                select(FieldModel)
                .where(FieldModel.field_id == field_id)
                .order_by(FieldModel.version.desc())
            )
        ).scalars().all()
        return [
            FieldVersionEntry(
                id=m.id,
                version=m.version,
                status=m.status,
                created_at=m.created_at,
            )
            for m in models
        ]
