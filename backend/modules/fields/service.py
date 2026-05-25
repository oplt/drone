from __future__ import annotations

from shapely.geometry import Polygon
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.fields.models import Field
from backend.modules.fields.repository import FieldRepository
from backend.modules.identity.models import User
from backend.modules.organizations.service import get_default_project


class FieldService:
    def __init__(self, repository: FieldRepository | None = None) -> None:
        self.repository = repository or FieldRepository()

    async def create(self, db: AsyncSession, *, user: User, name: str, polygon: Polygon) -> Field:
        project = await get_default_project(db, org_id=int(user.org_id)) if user.org_id else None
        return await self.repository.create(
            db,
            user=user,
            project_id=project.id if project else None,
            name=name,
            polygon=polygon,
        )

    async def list_owned(
        self, db: AsyncSession, *, user: User, query: str | None, limit: int
    ) -> list[Field]:
        return await self.repository.list_owned(db, user=user, query=query, limit=limit)

    async def get_owned(self, db: AsyncSession, *, field_id: int, user: User) -> Field | None:
        return await self.repository.get_owned(db, field_id=field_id, user=user)

    async def update(
        self,
        db: AsyncSession,
        *,
        field: Field,
        name: str | None,
        polygon: Polygon | None,
    ) -> Field:
        return await self.repository.update(db, field=field, name=name, polygon=polygon)

    async def delete(self, db: AsyncSession, *, field: Field) -> None:
        await self.repository.delete(db, field=field)


field_service = FieldService()
