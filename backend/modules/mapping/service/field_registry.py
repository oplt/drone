from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.fields.models import Field as FieldEntity
from backend.modules.identity.models import User
from backend.modules.mapping.models import FieldModel
from backend.modules.organizations.service import ownership_clause


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
        user: User,
    ) -> FieldEntity | None:
        return (
            await db.execute(
                select(FieldEntity)
                .where(FieldEntity.id == field_id)
                .where(
                    ownership_clause(
                        user=user,
                        owner_col=FieldEntity.owner_id,
                        org_col=FieldEntity.org_id,
                    )
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
    ) -> list[FieldVersionEntry]:
        models = (
            (
                await db.execute(
                    select(FieldModel)
                    .where(FieldModel.field_id == field_id)
                    .order_by(FieldModel.version.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            FieldVersionEntry(
                id=m.id,
                version=m.version,
                status=m.status,
                created_at=m.created_at,
            )
            for m in models
        ]
