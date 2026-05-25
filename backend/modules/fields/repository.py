from __future__ import annotations

from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.fields.models import Field
from backend.modules.identity.models import User
from backend.modules.organizations.service import ownership_clause


class FieldRepository:
    async def create(
        self,
        db: AsyncSession,
        *,
        user: User,
        project_id: int | None,
        name: str,
        polygon: Polygon,
    ) -> Field:
        field = Field(
            owner_id=user.id,
            org_id=user.org_id,
            project_id=project_id,
            name=name,
            boundary=from_shape(polygon, srid=4326),
            area_ha=None,
            centroid=from_shape(polygon.centroid, srid=4326),
        )
        db.add(field)
        await db.flush()
        await self._refresh_area(db, field)
        await db.commit()
        await db.refresh(field)
        return field

    async def list_owned(
        self, db: AsyncSession, *, user: User, query: str | None, limit: int
    ) -> list[Field]:
        stmt = (
            select(Field)
            .where(ownership_clause(user=user, owner_col=Field.owner_id, org_col=Field.org_id))
            .order_by(Field.id.desc())
            .limit(limit)
        )
        if query:
            stmt = stmt.where(Field.name.ilike(f"%{query}%"))
        return list((await db.execute(stmt)).scalars().all())

    async def get_owned(self, db: AsyncSession, *, field_id: int, user: User) -> Field | None:
        stmt = (
            select(Field)
            .where(Field.id == field_id)
            .where(ownership_clause(user=user, owner_col=Field.owner_id, org_col=Field.org_id))
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def update(
        self,
        db: AsyncSession,
        *,
        field: Field,
        name: str | None,
        polygon: Polygon | None,
    ) -> Field:
        if name is not None:
            field.name = name
        if polygon is not None:
            field.boundary = from_shape(polygon, srid=4326)
            field.centroid = from_shape(polygon.centroid, srid=4326)
            await db.flush()
            await self._refresh_area(db, field)
        await db.commit()
        await db.refresh(field)
        return field

    async def delete(self, db: AsyncSession, *, field: Field) -> None:
        await db.delete(field)
        await db.commit()

    @staticmethod
    async def _refresh_area(db: AsyncSession, field: Field) -> None:
        try:
            row = await db.execute(
                text(
                    "SELECT ST_Area(ST_Transform(boundary, 3857)) / 10000.0 "
                    "FROM fields WHERE id = :fid"
                ),
                {"fid": field.id},
            )
            field.area_ha = row.scalar()
        except Exception:
            field.area_ha = None
