# backend/db/livestock_repository.py
from __future__ import annotations

from typing import Optional, Dict, Any, List
from sqlalchemy import select, insert, func
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from backend.db.models import Herd, Animal, AnimalPosition, HerdTask, Geofence


class LivestockRepository:
    # ---------- Herds ----------
    async def create_herd(self, db: AsyncSession, *, name: str, pasture_geofence_id: Optional[int], metadata: Dict[str, Any]) -> Herd:
        herd = Herd(name=name, pasture_geofence_id=pasture_geofence_id, metadata=metadata or {})
        db.add(herd)
        await db.commit()
        await db.refresh(herd)
        return herd

    async def list_herds(self, db: AsyncSession, limit: int = 100) -> List[Herd]:
        res = await db.execute(select(Herd).order_by(Herd.id.desc()).limit(limit))
        return res.scalars().all()

    # ---------- Animals ----------
    async def create_animal(self, db: AsyncSession, *, herd_id: int, collar_id: str, name: Optional[str], species: str, metadata: Dict[str, Any]) -> Animal:
        animal = Animal(herd_id=herd_id, collar_id=collar_id, name=name, species=species, metadata=metadata or {})
        db.add(animal)
        await db.commit()
        await db.refresh(animal)
        return animal

    async def get_animal_by_collar(self, db: AsyncSession, *, collar_id: str) -> Optional[Animal]:
        res = await db.execute(select(Animal).where(Animal.collar_id == collar_id))
        return res.scalar_one_or_none()

    async def list_animals(self, db: AsyncSession, herd_id: Optional[int] = None, limit: int = 200) -> List[Animal]:
        stmt = select(Animal)
        if herd_id is not None:
            stmt = stmt.where(Animal.herd_id == herd_id)
        res = await db.execute(stmt.order_by(Animal.id.desc()).limit(limit))
        return res.scalars().all()

    # ---------- Positions ----------
    async def add_position(self, db: AsyncSession, *, animal_id: int, lat: float, lon: float, alt: Optional[float], speed_mps: Optional[float], activity: Optional[float], source: str, raw: Dict[str, Any]) -> AnimalPosition:
        pt = from_shape(Point(float(lon), float(lat)), srid=4326)
        pos = AnimalPosition(
            animal_id=animal_id,
            lat=float(lat),
            lon=float(lon),
            alt=(None if alt is None else float(alt)),
            speed_mps=(None if speed_mps is None else float(speed_mps)),
            activity=(None if activity is None else float(activity)),
            point=pt,
            source=source or "collar",
            raw=raw or {},
        )
        db.add(pos)
        await db.commit()
        await db.refresh(pos)
        return pos

    async def latest_positions_for_herd(self, db: AsyncSession, *, herd_id: int) -> List[Dict[str, Any]]:
        """
        Returns latest position per animal in herd.
        Uses DISTINCT ON-like pattern via subquery max(created_at).
        """
        subq = (
            select(
                AnimalPosition.animal_id,
                func.max(AnimalPosition.created_at).label("mx")
            )
            .join(Animal, Animal.id == AnimalPosition.animal_id)
            .where(Animal.herd_id == herd_id)
            .group_by(AnimalPosition.animal_id)
            .subquery()
        )

        stmt = (
            select(AnimalPosition, Animal)
            .join(subq, (subq.c.animal_id == AnimalPosition.animal_id) & (subq.c.mx == AnimalPosition.created_at))
            .join(Animal, Animal.id == AnimalPosition.animal_id)
        )

        res = await db.execute(stmt)
        out: List[Dict[str, Any]] = []
        for pos, animal in res.all():
            out.append({
                "animal_id": animal.id,
                "collar_id": animal.collar_id,
                "animal_name": animal.name,
                "species": animal.species,
                "lat": pos.lat,
                "lon": pos.lon,
                "alt": pos.alt,
                "created_at": pos.created_at,
            })
        return out

    # ---------- Tasks ----------
    async def create_task(self, db: AsyncSession, *, herd_id: int, type: str, params: Dict[str, Any]) -> HerdTask:
        task = HerdTask(herd_id=herd_id, type=type, status="created", params=params or {}, result={})
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    async def set_task_status(self, db: AsyncSession, *, task_id: int, status: str, result: Optional[Dict[str, Any]] = None, flight_id: Optional[int] = None) -> HerdTask:
        res = await db.execute(select(HerdTask).where(HerdTask.id == task_id))
        task = res.scalar_one()
        task.status = status
        if result is not None:
            task.result = result
        if flight_id is not None:
            task.flight_id = flight_id
        await db.commit()
        await db.refresh(task)
        return task

    async def list_tasks(self, db: AsyncSession, herd_id: int, limit: int = 100) -> List[HerdTask]:
        res = await db.execute(
            select(HerdTask)
            .where(HerdTask.herd_id == herd_id)
            .order_by(HerdTask.id.desc())
            .limit(limit)
        )
        return res.scalars().all()

    # ---------- Pasture polygon ----------
    async def get_pasture_geofence(self, db: AsyncSession, geofence_id: int) -> Optional[Geofence]:
        res = await db.execute(select(Geofence).where(Geofence.id == geofence_id))
        return res.scalar_one_or_none()