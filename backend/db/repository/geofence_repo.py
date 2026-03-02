from __future__ import annotations
from sqlalchemy import select, func
import logging
from ..session import Session
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.models import Geofence
from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon, Point


logger = logging.getLogger(__name__)



class GeofenceRepository:

    def __init__(self) -> None:
        self._session_factory = Session


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
            .where(Geofence.is_active == True)
            .where(func.ST_Contains(Geofence.polygon, point))
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None


    async def validate_mission_waypoints(
            db: AsyncSession,
            geofence_name: str,
            waypoints: list[tuple[float, float]],
    ):

        for lat, lon in waypoints:
            inside = await is_point_inside_geofence(
                db,
                geofence_name=geofence_name,
                lat=lat,
                lon=lon,
            )
            if not inside:
                return False

        return True
