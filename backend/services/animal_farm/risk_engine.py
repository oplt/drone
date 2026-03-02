# backend/domain/livestock/risk_engine.py
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from shapely.geometry import Point
from geoalchemy2.shape import to_shape

from backend.db.models import Animal, AnimalPosition, Geofence


class RiskEngine:
    """
    Start with deterministic rules (fast + explainable):
      - boundary exit: latest point not inside pasture geofence polygon
      - isolation: animal far from nearest neighbor beyond threshold
    """

    async def boundary_exit_alerts(
            self,
            db: AsyncSession,
            *,
            herd_id: int,
            pasture_geofence_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        if not pasture_geofence_id:
            return []

        gf = (await db.execute(select(Geofence).where(Geofence.id == pasture_geofence_id))).scalar_one_or_none()
        if not gf:
            return []

        poly = to_shape(gf.polygon)

        # Get animals
        animals = (await db.execute(select(Animal).where(Animal.herd_id == herd_id, Animal.is_active == True))).scalars().all()
        if not animals:
            return []

        alerts: List[Dict[str, Any]] = []

        # For each animal fetch latest position (simple but fine for MVP)
        for a in animals:
            pos = (
                await db.execute(
                    select(AnimalPosition)
                    .where(AnimalPosition.animal_id == a.id)
                    .order_by(AnimalPosition.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()

            if not pos:
                continue

            inside = poly.contains(Point(float(pos.lon), float(pos.lat)))
            if not inside:
                alerts.append({
                    "type": "boundary_exit",
                    "severity": "high",
                    "animal_id": a.id,
                    "collar_id": a.collar_id,
                    "lat": pos.lat,
                    "lon": pos.lon,
                    "message": "Animal is outside pasture geofence",
                })

        return alerts

    async def isolation_alerts(
            self,
            db: AsyncSession,
            *,
            herd_id: int,
            threshold_m: float = 250.0,
    ) -> List[Dict[str, Any]]:
        """
        Uses PostGIS ST_DistanceSphere between latest points.
        For MVP: compute nearest-neighbor distance for each animal.
        """
        # Latest position per animal in herd (subquery max(created_at))
        subq = (
            select(
                AnimalPosition.animal_id,
                func.max(AnimalPosition.created_at).label("mx")
            )
            .join(Animal, Animal.id == AnimalPosition.animal_id)
            .where(Animal.herd_id == herd_id, Animal.is_active == True)
            .group_by(AnimalPosition.animal_id)
            .subquery()
        )

        latest = (
            await db.execute(
                select(AnimalPosition, Animal)
                .join(subq, (subq.c.animal_id == AnimalPosition.animal_id) & (subq.c.mx == AnimalPosition.created_at))
                .join(Animal, Animal.id == AnimalPosition.animal_id)
            )
        ).all()

        if len(latest) < 2:
            return []

        # Pairwise compute nearest neighbor distance using PostGIS ST_DistanceSphere
        alerts: List[Dict[str, Any]] = []

        positions = [(pos, animal) for (pos, animal) in latest]
        for pos_a, animal_a in positions:
            # Find nearest other
            best = None
            for pos_b, animal_b in positions:
                if animal_b.id == animal_a.id:
                    continue
                # ST_DistanceSphere(ST_MakePoint(lon,lat), ST_MakePoint(lon,lat))
                dist = (
                    await db.execute(
                        select(
                            func.ST_DistanceSphere(
                                func.ST_MakePoint(pos_a.lon, pos_a.lat),
                                func.ST_MakePoint(pos_b.lon, pos_b.lat),
                            )
                        )
                    )
                ).scalar_one()

                if best is None or dist < best:
                    best = float(dist)

            if best is not None and best > float(threshold_m):
                alerts.append({
                    "type": "isolation",
                    "severity": "medium",
                    "animal_id": animal_a.id,
                    "collar_id": animal_a.collar_id,
                    "lat": pos_a.lat,
                    "lon": pos_a.lon,
                    "distance_to_nearest_m": best,
                    "message": f"Animal isolated: nearest neighbor {best:.0f}m away",
                })

        return alerts