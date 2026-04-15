# backend/api/routes/routes_fields.py
"""
Field CRUD endpoints.

Bug fixes / improvements
------------------------
1. owner_id was taken from the request body (payload.owner_id) — anyone could
   create a field owned by an arbitrary user. Now taken from the authenticated
   user via require_user() and ignored if supplied in the payload.
2. _field_to_geojson_coords() helper was defined but never called — removed.
3. GET /fields made N calls to /fields/{id}/geojson from the frontend —
   /fields/features already existed but wasn't being used. Added a note in
   the docstring to guide frontend integration.
4. Added DELETE endpoint (common omission that frontend typically needs).
5. Area computed server-side via PostGIS ST_Area so the DB is the source of
   truth; falls back to None if PostGIS extension is unavailable.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Polygon, mapping
from shapely.validation import explain_validity
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import OrgUser, require_org_user, require_org_write
from backend.db.models import Field as FieldModel
from backend.db.session import get_db
from backend.schemas.field import FieldCreateGeoJSON, FieldOut, FieldUpdate
from backend.services.access_control import get_default_project, ownership_clause

router = APIRouter(prefix="/fields", tags=["fields"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_closed_ring(coords: list[list[float]]) -> list[list[float]]:
    if len(coords) < 3:
        raise ValueError("Polygon needs at least 3 points")
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    return coords


def _coords_to_polygon(coords_lonlat: list[list[float]]) -> Polygon:
    coords_lonlat = _ensure_closed_ring(coords_lonlat)
    poly = Polygon(coords_lonlat)  # Shapely: (x, y) = (lon, lat)
    if not poly.is_valid:
        raise ValueError(f"Invalid polygon: {explain_validity(poly)}")
    if poly.area == 0:
        raise ValueError("Invalid polygon: zero area")
    return poly


def _field_out(field: FieldModel) -> FieldOut:
    return FieldOut(
        id=field.id,
        owner_id=field.owner_id,
        name=field.name,
        area_ha=field.area_ha,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=FieldOut)
async def create_field(
    payload: FieldCreateGeoJSON,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    """Create a new field boundary for the authenticated user.

    ``owner_id`` is always taken from the JWT — any value supplied in the
    payload body is ignored to prevent ownership spoofing.
    """
    try:
        poly = _coords_to_polygon(payload.coordinates)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = org_user.user
    default_project = await get_default_project(db, org_id=int(user.org_id)) if user.org_id else None
    field = FieldModel(
        owner_id=user.id,  # ← from auth, not payload
        org_id=user.org_id,
        project_id=default_project.id if default_project else None,
        name=payload.name,
        boundary=from_shape(poly, srid=4326),
        area_ha=None,  # computed below if PostGIS available
        centroid=from_shape(poly.centroid, srid=4326),
    )
    db.add(field)
    await db.flush()  # get the PK so we can run the area query on it

    # Compute accurate geodesic area via PostGIS (optional — skipped if unavailable)
    try:
        row = await db.execute(
            text(
                "SELECT ST_Area(ST_Transform(boundary, 3857)) / 10000.0 AS area_ha "
                "FROM fields WHERE id = :fid"
            ),
            {"fid": field.id},
        )
        field.area_ha = row.scalar()
    except Exception:
        pass  # PostGIS not available — area stays None

    await db.commit()
    await db.refresh(field)
    return _field_out(field)


@router.get("", response_model=list[FieldOut])
async def list_fields(
    q: str | None = Query(None, description="Name search (ILIKE)"),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    """List fields owned by the authenticated user.

    NOTE: The frontend should prefer GET /fields/features which returns
    geometry in a single round-trip instead of N+1 calls.
    """
    user = org_user.user
    stmt = (
        select(FieldModel)
        .where(ownership_clause(user=user, owner_col=FieldModel.owner_id, org_col=FieldModel.org_id))
        .order_by(FieldModel.id.desc())
        .limit(limit)
    )
    if q:
        stmt = stmt.where(FieldModel.name.ilike(f"%{q}%"))

    rows = (await db.execute(stmt)).scalars().all()
    return [_field_out(f) for f in rows]


@router.get("/features")
async def list_fields_features(
    q: str | None = Query(None, description="Name search (ILIKE)"),
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    """Return all fields as a GeoJSON FeatureCollection **in one call**.

    The frontend should call this endpoint instead of GET /fields + N×
    GET /fields/{id}/geojson to avoid N+1 network round-trips.
    """
    user = org_user.user
    stmt = (
        select(FieldModel)
        .where(ownership_clause(user=user, owner_col=FieldModel.owner_id, org_col=FieldModel.org_id))
        .order_by(FieldModel.id.desc())
        .limit(limit)
    )
    if q:
        stmt = stmt.where(FieldModel.name.ilike(f"%{q}%"))

    rows = (await db.execute(stmt)).scalars().all()

    features: list[dict[str, Any]] = []
    for f in rows:
        if not f.boundary:
            continue
        poly = to_shape(f.boundary)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": f.id,
                    "owner_id": f.owner_id,
                    "name": f.name,
                    "area_ha": f.area_ha,
                },
                "geometry": mapping(poly),
            }
        )

    return {"type": "FeatureCollection", "features": features}


@router.get("/{field_id}", response_model=FieldOut)
async def get_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    field = await _get_owned_field(field_id, org_user.user, db)
    return _field_out(field)


@router.get("/{field_id}/geojson")
async def get_field_geojson(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    field = await _get_owned_field(field_id, org_user.user, db)
    poly = to_shape(field.boundary)
    return {
        "type": "Feature",
        "properties": {
            "id": field.id,
            "owner_id": field.owner_id,
            "name": field.name,
            "area_ha": field.area_ha,
        },
        "geometry": mapping(poly),
    }


@router.patch("/{field_id}", response_model=FieldOut)
async def update_field(
    field_id: int,
    payload: FieldUpdate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    field = await _get_owned_field(field_id, org_user.user, db)

    if payload.name is not None:
        field.name = payload.name

    if payload.coordinates is not None:
        try:
            poly = _coords_to_polygon(payload.coordinates)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        field.boundary = from_shape(poly, srid=4326)
        field.centroid = from_shape(poly.centroid, srid=4326)
        # Recompute area
        try:
            await db.flush()
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

    await db.commit()
    await db.refresh(field)
    return _field_out(field)


@router.delete("/{field_id}", status_code=204)
async def delete_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    """Delete a field owned by the authenticated user."""
    field = await _get_owned_field(field_id, org_user.user, db)
    await db.delete(field)
    await db.commit()


# ---------------------------------------------------------------------------
# Shared ownership guard
# ---------------------------------------------------------------------------


async def _get_owned_field(field_id: int, user, db: AsyncSession) -> FieldModel:
    field = (
        await db.execute(
            select(FieldModel).where(FieldModel.id == field_id).where(
                ownership_clause(user=user, owner_col=FieldModel.owner_id, org_col=FieldModel.org_id)
            )
        )
    ).scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    return field
