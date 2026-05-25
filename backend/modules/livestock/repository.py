from __future__ import annotations

from typing import Any

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.livestock.models import Animal, AnimalPosition, Herd, HerdTask


class LivestockRepository:
    async def create_herd(
        self,
        db: AsyncSession,
        *,
        org_id: int,
        name: str,
        pasture_geofence_id: int | None,
        metadata: dict[str, Any],
    ) -> Herd:
        herd = Herd(
            org_id=org_id,
            name=name,
            pasture_geofence_id=pasture_geofence_id,
            meta_data=metadata or {},
        )
        db.add(herd)
        await db.commit()
        await db.refresh(herd)
        return herd

    async def get_herd(self, db: AsyncSession, *, org_id: int, herd_id: int) -> Herd | None:
        row = await db.execute(select(Herd).where(Herd.id == herd_id, Herd.org_id == org_id))
        return row.scalar_one_or_none()

    async def list_herds(self, db: AsyncSession, *, org_id: int, limit: int = 100) -> list[Herd]:
        rows = await db.execute(
            select(Herd).where(Herd.org_id == org_id).order_by(Herd.id.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def create_animal(
        self,
        db: AsyncSession,
        *,
        herd_id: int,
        collar_id: str,
        name: str | None,
        species: str,
        metadata: dict[str, Any],
    ) -> Animal:
        animal = Animal(
            herd_id=herd_id,
            collar_id=collar_id,
            name=name,
            species=species,
            meta_data=metadata or {},
        )
        db.add(animal)
        await db.commit()
        await db.refresh(animal)
        return animal

    async def get_animal_by_collar(
        self, db: AsyncSession, *, org_id: int, collar_id: str
    ) -> Animal | None:
        rows = await db.execute(
            select(Animal)
            .join(Herd, Animal.herd_id == Herd.id)
            .where(Animal.collar_id == collar_id, Herd.org_id == org_id)
        )
        return rows.scalar_one_or_none()

    async def list_animals(
        self, db: AsyncSession, *, org_id: int, herd_id: int | None = None, limit: int = 200
    ) -> list[Animal]:
        stmt = select(Animal).join(Herd, Animal.herd_id == Herd.id).where(Herd.org_id == org_id)
        if herd_id is not None:
            stmt = stmt.where(Animal.herd_id == herd_id)
        rows = await db.execute(stmt.order_by(Animal.id.desc()).limit(limit))
        return list(rows.scalars().all())

    async def add_position(
        self,
        db: AsyncSession,
        *,
        animal_id: int,
        lat: float,
        lon: float,
        alt: float | None,
        speed_mps: float | None,
        activity: float | None,
        source: str,
        raw: dict[str, Any],
    ) -> AnimalPosition:
        pos = AnimalPosition(
            animal_id=animal_id,
            lat=float(lat),
            lon=float(lon),
            alt=None if alt is None else float(alt),
            speed_mps=None if speed_mps is None else float(speed_mps),
            activity=None if activity is None else float(activity),
            point=from_shape(Point(float(lon), float(lat)), srid=4326),
            source=source or "collar",
            raw=raw or {},
        )
        db.add(pos)
        await db.commit()
        await db.refresh(pos)
        return pos

    async def latest_positions_for_herd(
        self, db: AsyncSession, *, org_id: int, herd_id: int
    ) -> list[dict[str, Any]]:
        subq = (
            select(AnimalPosition.animal_id, func.max(AnimalPosition.created_at).label("mx"))
            .join(Animal, Animal.id == AnimalPosition.animal_id)
            .join(Herd, Herd.id == Animal.herd_id)
            .where(Animal.herd_id == herd_id, Herd.org_id == org_id)
            .group_by(AnimalPosition.animal_id)
            .subquery()
        )
        rows = await db.execute(
            select(AnimalPosition, Animal)
            .join(
                subq,
                (subq.c.animal_id == AnimalPosition.animal_id)
                & (subq.c.mx == AnimalPosition.created_at),
            )
            .join(Animal, Animal.id == AnimalPosition.animal_id)
        )
        return [
            {
                "animal_id": animal.id,
                "collar_id": animal.collar_id,
                "animal_name": animal.name,
                "species": animal.species,
                "lat": pos.lat,
                "lon": pos.lon,
                "alt": pos.alt,
                "created_at": pos.created_at,
            }
            for pos, animal in rows.all()
        ]

    async def create_task(
        self, db: AsyncSession, *, herd_id: int, type: str, params: dict[str, Any]
    ) -> HerdTask:
        task = HerdTask(
            herd_id=herd_id, type=type, status="created", params=params or {}, result={}
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    async def get_task(self, db: AsyncSession, *, org_id: int, task_id: int) -> HerdTask | None:
        rows = await db.execute(
            select(HerdTask)
            .join(Herd, HerdTask.herd_id == Herd.id)
            .where(HerdTask.id == task_id, Herd.org_id == org_id)
        )
        return rows.scalar_one_or_none()

    async def list_tasks(
        self, db: AsyncSession, *, org_id: int, herd_id: int, limit: int = 100
    ) -> list[HerdTask]:
        rows = await db.execute(
            select(HerdTask)
            .join(Herd, HerdTask.herd_id == Herd.id)
            .where(HerdTask.herd_id == herd_id, Herd.org_id == org_id)
            .order_by(HerdTask.id.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())
