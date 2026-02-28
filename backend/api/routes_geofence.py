from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.db.session import get_db
from backend.db.models import Geofence
from shapely.geometry import Polygon, mapping
from geoalchemy2.shape import from_shape, to_shape
from backend.schemas.geofence import GeofenceCreateGeoJSON, GeofenceOut, GeofenceUpdate


router = APIRouter(prefix="/geofences", tags=["geofences"])


def _ensure_closed_ring(coords: List[List[float]]) -> List[List[float]]:
    if len(coords) < 3:
        raise ValueError("Polygon needs at least 3 points")
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    return coords


def _coords_to_polygon(coords_lonlat: List[List[float]]) -> Polygon:
    coords_lonlat = _ensure_closed_ring(coords_lonlat)
    # Shapely uses (x,y) = (lon,lat)
    return Polygon(coords_lonlat)


def _geofence_to_geojson_coords(gf: Geofence) -> List[List[float]]:
    poly = to_shape(gf.polygon)  # shapely Polygon
    # Return exterior ring as [[lon,lat], ...]
    return [[float(x), float(y)] for (x, y) in list(poly.exterior.coords)]


# -------------------------
# Routes
# -------------------------

@router.post("", response_model=GeofenceOut)
async def create_geofence(
        payload: GeofenceCreateGeoJSON,
        db: AsyncSession = Depends(get_db),
):
    try:
        poly = _coords_to_polygon(payload.coordinates)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid polygon: {e}")

    gf = Geofence(
        name=payload.name,
        polygon=from_shape(poly, srid=4326),
        min_alt_m=payload.min_alt_m,
        max_alt_m=payload.max_alt_m,
        is_active=payload.is_active,
        source=payload.source,
        source_ref=payload.source_ref,
        metadata=payload.metadata,
    )

    db.add(gf)
    await db.commit()
    await db.refresh(gf)
    return gf


@router.get("", response_model=List[GeofenceOut])
async def list_geofences(
        active: Optional[bool] = Query(None, description="Filter by active status"),
        q: Optional[str] = Query(None, description="Name search (ILIKE)"),
        limit: int = Query(50, ge=1, le=500),
        db: AsyncSession = Depends(get_db),
):
    stmt = select(Geofence)

    if active is not None:
        stmt = stmt.where(Geofence.is_active == active)
    if q:
        stmt = stmt.where(Geofence.name.ilike(f"%{q}%"))

    stmt = stmt.order_by(Geofence.id.desc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.get("/{geofence_id}", response_model=GeofenceOut)
async def get_geofence(
        geofence_id: int,
        db: AsyncSession = Depends(get_db),
):
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")
    return gf


@router.get("/{geofence_id}/geojson")
async def get_geofence_geojson(
        geofence_id: int,
        db: AsyncSession = Depends(get_db),
):
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    poly = to_shape(gf.polygon)
    return {
        "type": "Feature",
        "properties": {
            "id": gf.id,
            "name": gf.name,
            "min_alt_m": gf.min_alt_m,
            "max_alt_m": gf.max_alt_m,
            "is_active": gf.is_active,
            "source": gf.source,
            "source_ref": gf.source_ref,
            "metadata": gf.metadata or {},
        },
        "geometry": mapping(poly),  # GeoJSON geometry
    }


@router.get("/{geofence_id}/latlon")
async def get_geofence_latlon_ring(
        geofence_id: int,
        db: AsyncSession = Depends(get_db),
):
    """
    Returns ring in the exact order your current preflight polygon code expects: [(lat,lon),...]
    (Your Python point-in-polygon uses lat/lon ordering.) :contentReference[oaicite:3]{index=3}
    """
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    coords_lonlat = _geofence_to_geojson_coords(gf)
    coords_latlon = [[c[1], c[0]] for c in coords_lonlat]  # [lat,lon]
    return {"id": gf.id, "name": gf.name, "polygon": coords_latlon}


@router.patch("/{geofence_id}", response_model=GeofenceOut)
async def update_geofence(
        geofence_id: int,
        payload: GeofenceUpdate,
        db: AsyncSession = Depends(get_db),
):
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    if payload.name is not None:
        gf.name = payload.name
    if payload.min_alt_m is not None:
        gf.min_alt_m = payload.min_alt_m
    if payload.max_alt_m is not None:
        gf.max_alt_m = payload.max_alt_m
    if payload.source is not None:
        gf.source = payload.source
    if payload.source_ref is not None:
        gf.source_ref = payload.source_ref
    if payload.metadata is not None:
        gf.metadata = payload.metadata
    if payload.is_active is not None:
        gf.is_active = payload.is_active

    if payload.coordinates is not None:
        try:
            poly = _coords_to_polygon(payload.coordinates)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid polygon: {e}")
        gf.polygon = from_shape(poly, srid=4326)

    await db.commit()
    await db.refresh(gf)
    return gf


@router.post("/{geofence_id}/activate", response_model=GeofenceOut)
async def activate_geofence(
        geofence_id: int,
        db: AsyncSession = Depends(get_db),
):
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    gf.is_active = True
    await db.commit()
    await db.refresh(gf)
    return gf


@router.post("/{geofence_id}/deactivate", response_model=GeofenceOut)
async def deactivate_geofence(
        geofence_id: int,
        db: AsyncSession = Depends(get_db),
):
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    gf.is_active = False
    await db.commit()
    await db.refresh(gf)
    return gf


@router.delete("/{geofence_id}")
async def delete_geofence(
        geofence_id: int,
        db: AsyncSession = Depends(get_db),
):
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    await db.delete(gf)
    await db.commit()
    return {"ok": True, "deleted_id": geofence_id}


@router.post("/{geofence_id}/contains")
async def contains_point(
        geofence_id: int,
        lat: float = Query(...),
        lon: float = Query(...),
        db: AsyncSession = Depends(get_db),
):
    """
    Spatial containment check in PostGIS (fast + correct).
    """
    gf = (await db.execute(select(Geofence).where(Geofence.id == geofence_id))).scalar_one_or_none()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    # ST_Contains(polygon, ST_SetSRID(ST_MakePoint(lon,lat),4326))
    stmt = select(
        func.ST_Contains(
            gf.polygon,
            func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326),
        )
    )
    inside = (await db.execute(stmt)).scalar_one()
    return {"id": geofence_id, "lat": lat, "lon": lon, "inside": bool(inside)}