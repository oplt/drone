# backend/domain/livestock/risk_engine.py
from __future__ import annotations

import math
from typing import Any

from scipy.spatial import cKDTree
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.types.geo import haversine_km
from backend.modules.geofences.models import Geofence
from backend.modules.livestock.models import Animal, AnimalPosition


class RiskEngine:
    """
    Start with deterministic rules (fast + explainable):
      - boundary exit: latest point not inside pasture geofence polygon
      - isolation: animal far from nearest neighbor beyond threshold
    """

    @staticmethod
    def _latest_positions_statement(
        *, herd_id: int | None = None, herd_ids: list[int] | None = None
    ):
        """Build one deterministic latest-position query for active herd animals."""
        herd_filter = (
            Animal.herd_id == herd_id
            if herd_id is not None
            else Animal.herd_id.in_(herd_ids or [])
        )
        ranked_positions = (
            select(
                AnimalPosition.id.label("position_id"),
                func.row_number()
                .over(
                    partition_by=AnimalPosition.animal_id,
                    order_by=(AnimalPosition.created_at.desc(), AnimalPosition.id.desc()),
                )
                .label("position_rank"),
            )
            .join(Animal, Animal.id == AnimalPosition.animal_id)
            .where(herd_filter, Animal.is_active.is_(True))
            .subquery()
        )
        return (
            select(AnimalPosition, Animal)
            .join(ranked_positions, ranked_positions.c.position_id == AnimalPosition.id)
            .join(Animal, Animal.id == AnimalPosition.animal_id)
            .where(ranked_positions.c.position_rank == 1)
        )

    async def boundary_exit_alerts(
        self,
        db: AsyncSession,
        *,
        herd_id: int,
        pasture_geofence_id: int | None,
    ) -> list[dict[str, Any]]:
        if not pasture_geofence_id:
            return []

        point = func.ST_SetSRID(
            func.ST_MakePoint(AnimalPosition.lon, AnimalPosition.lat), 4326
        )
        latest_rows = (
            await db.execute(
                self._latest_positions_statement(herd_id=herd_id)
                .join(Geofence, Geofence.id == pasture_geofence_id)
                .where(
                    Geofence.id == pasture_geofence_id,
                    ~func.ST_Contains(Geofence.polygon, point),
                )
            )
        ).all()

        alerts: list[dict[str, Any]] = []

        for pos, animal in latest_rows:
            alerts.append(
                {
                    "type": "boundary_exit",
                    "severity": "high",
                    "animal_id": animal.id,
                    "collar_id": animal.collar_id,
                    "lat": pos.lat,
                    "lon": pos.lon,
                    "message": "Animal is outside pasture geofence",
                }
            )

        return alerts

    async def isolation_alerts(
        self,
        db: AsyncSession,
        *,
        herd_id: int,
        threshold_m: float = 250.0,
    ) -> list[dict[str, Any]]:
        """
        Fetches latest points once, then computes nearest-neighbor distances locally.
        """
        latest = (
            await db.execute(self._latest_positions_statement(herd_id=herd_id))
        ).all()
        return self._isolation_alerts_from_rows(latest, threshold_m=threshold_m)

    async def isolation_alerts_for_herds(
        self,
        db: AsyncSession,
        *,
        herd_ids: list[int],
        threshold_m: float = 250.0,
    ) -> list[dict[str, Any]]:
        """Evaluate all configured herds with one latest-position query."""
        normalized_ids = sorted({int(herd_id) for herd_id in herd_ids if int(herd_id) > 0})
        if not normalized_ids:
            return []
        latest = (
            await db.execute(self._latest_positions_statement(herd_ids=normalized_ids))
        ).all()
        grouped: dict[int, list[tuple[AnimalPosition, Animal]]] = {}
        for position, animal in latest:
            grouped.setdefault(int(animal.herd_id), []).append((position, animal))
        alerts: list[dict[str, Any]] = []
        for herd_rows in grouped.values():
            alerts.extend(self._isolation_alerts_from_rows(herd_rows, threshold_m=threshold_m))
        return alerts

    @staticmethod
    def _isolation_alerts_from_rows(
        latest: list[tuple[AnimalPosition, Animal]], *, threshold_m: float
    ) -> list[dict[str, Any]]:

        if len(latest) < 2:
            return []

        # Latest positions are fetched once. A local tangent-plane KD-tree reduces
        # nearest-neighbor search from O(n²) to O(n log n); exact haversine distance
        # is still used for the threshold and response.
        alerts: list[dict[str, Any]] = []

        positions = [(pos, animal) for (pos, animal) in latest]
        mean_lat = sum(float(pos.lat) for pos, _ in positions) / len(positions)
        lon_scale = max(1e-6, math.cos(math.radians(mean_lat)))
        # Equirectangular metres; only candidate selection uses this approximation.
        points = [
            (float(pos.lon) * 111_320.0 * lon_scale, float(pos.lat) * 110_540.0)
            for pos, _ in positions
        ]
        _, nearest_indexes = cKDTree(points).query(points, k=2)

        for index, ((pos_a, animal_a), nearest) in enumerate(
            zip(positions, nearest_indexes, strict=True)
        ):
            neighbor_index = int(nearest[1]) if len(nearest) > 1 else -1
            if neighbor_index < 0 or neighbor_index == index:
                continue
            pos_b, _ = positions[neighbor_index]
            best = haversine_km(
                float(pos_a.lat),
                float(pos_a.lon),
                float(pos_b.lat),
                float(pos_b.lon),
            ) * 1000.0

            if best > float(threshold_m):
                alerts.append(
                    {
                        "type": "isolation",
                        "severity": "medium",
                        "animal_id": animal_a.id,
                        "herd_id": animal_a.herd_id,
                        "collar_id": animal_a.collar_id,
                        "lat": pos_a.lat,
                        "lon": pos_a.lon,
                        "distance_to_nearest_m": best,
                        "message": f"Animal isolated: nearest neighbor {best:.0f}m away",
                    }
                )

        return alerts
