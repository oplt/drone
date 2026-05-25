from __future__ import annotations

import logging

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, Polygon
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import Session
from backend.modules.geofences.models import Geofence

logger = logging.getLogger(__name__)


class GeofenceRepository:
    def __init__(self) -> None:
        self._session_factory = Session

    @staticmethod
    async def save_geofence_geojson(
        db: AsyncSession,
        *,
        name: str,
        coordinates_lonlat: list[list[float]],
        min_alt_m: float | None = None,
        max_alt_m: float | None = None,
    ):

        # GeoJSON gives [lon, lat]
        polygon = Polygon(coordinates_lonlat)

        geofence = Geofence(
            name=name,
            polygon=from_shape(polygon, srid=4326),
            min_alt_m=min_alt_m,
            max_alt_m=max_alt_m,
        )

        db.add(geofence)
        await db.commit()
        await db.refresh(geofence)

        return geofence

    @staticmethod
    async def is_point_inside_geofence(
        db: AsyncSession,
        *,
        geofence_name: str,
        lat: float,
        lon: float,
    ) -> bool:

        point = from_shape(Point(lon, lat), srid=4326)

        stmt = (
            select(Geofence.id)
            .where(Geofence.name == geofence_name)
            .where(Geofence.is_active.is_(True))
            .where(func.ST_Contains(Geofence.polygon, point))
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def validate_mission_waypoints(
        db: AsyncSession,
        geofence_name: str,
        waypoints: list[tuple[float, float]],
    ):

        for lat, lon in waypoints:
            inside = await GeofenceRepository.is_point_inside_geofence(
                db,
                geofence_name=geofence_name,
                lat=lat,
                lon=lon,
            )
            if not inside:
                return False

        return True
