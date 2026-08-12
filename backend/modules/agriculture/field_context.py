from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Point, Polygon, shape
from shapely.validation import explain_validity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.field_context_models import AgricultureFieldBoundaryRevision, AgricultureFieldZone
from backend.modules.agriculture.models import new_id
from backend.modules.fields.service import field_service
from backend.modules.identity.dependencies import OrgUser, require_mission_exec, require_org_user

router = APIRouter(prefix="/agriculture", tags=["agriculture-field-context"])


class BoundaryIn(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]] = Field(..., min_length=1)


class FieldContextCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    boundary: dict[str, Any]


class BoundaryUpdate(BaseModel):
    boundary: dict[str, Any]
    reason: str | None = Field(default=None, max_length=500)


class ZoneIn(BaseModel):
    zone_type: Literal["exclusion", "obstacle"]
    geometry: dict[str, Any]
    name: str = Field(default="", max_length=128)
    kind: str = Field(default="unknown", max_length=64)
    radius_m: float | None = Field(default=None, gt=0, le=500)
    height_m: float | None = Field(default=None, ge=0, le=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ZoneOut(ZoneIn):
    id: str
    revision: int
    created_at: datetime


class BoundaryOut(BaseModel):
    revision: int
    boundary: dict[str, Any]
    area_ha: float
    created_at: datetime


class FieldContextOut(BaseModel):
    field_id: int
    name: str
    area_ha: float | None
    boundary: dict[str, Any]
    current_revision: int
    revisions: list[BoundaryOut]
    zones: list[ZoneOut]


def _geometry(payload: dict[str, Any], *, field_name: str) -> Polygon | Point:
    crs = payload.get("crs")
    if crs:
        name = str((crs.get("properties") or {}).get("name", "")) if isinstance(crs, dict) else str(crs)
        if "4326" not in name.upper() and "WGS84" not in name.upper() and "WGS 84" not in name.upper():
            raise HTTPException(status_code=422, detail={"code": "AGRICULTURE_CRS_UNSUPPORTED", "field": field_name, "message": "Boundary CRS must be EPSG:4326 (WGS84)."})
    geometry = payload.get("geometry", payload)
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "Point"}:
        raise HTTPException(status_code=422, detail={"code": "AGRICULTURE_GEOMETRY_TYPE_INVALID", "field": field_name, "message": "Expected a GeoJSON Polygon or Point."})
    try:
        parsed = shape(geometry)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "AGRICULTURE_GEOMETRY_INVALID", "field": field_name, "message": str(exc)}) from exc
    coords = list(parsed.coords) if isinstance(parsed, Point) else [coord for ring in parsed.exterior.coords for coord in [ring]]
    if any(len(coord) < 2 or not (-180 <= coord[0] <= 180 and -90 <= coord[1] <= 90) for coord in coords):
        raise HTTPException(status_code=422, detail={"code": "AGRICULTURE_COORDINATES_INVALID", "field": field_name, "message": "Coordinates must be WGS84 longitude/latitude."})
    if isinstance(parsed, Polygon) and (parsed.is_empty or parsed.area <= 0 or not parsed.is_valid):
        reason = explain_validity(parsed)
        raise HTTPException(status_code=422, detail={"code": "AGRICULTURE_GEOMETRY_INVALID", "field": field_name, "message": reason})
    return parsed


def _boundary_payload(value: dict[str, Any]) -> dict[str, Any]:
    geometry = value.get("geometry", value)
    _geometry(value, field_name="boundary")
    return {"type": "Polygon", "coordinates": geometry["coordinates"]}


def _area_ha(polygon: Polygon) -> float:
    # At field scale this is a stable fallback when the optional geodesic package is absent.
    lat = sum(point[1] for point in polygon.exterior.coords) / len(polygon.exterior.coords)
    meters_per_degree = 111_320.0
    import math
    return abs(polygon.area * meters_per_degree * meters_per_degree * math.cos(math.radians(lat)) / 10_000)


async def _owned(field_id: int, user: OrgUser, db: AsyncSession):
    field = await field_service.get_owned(db, field_id=field_id, user=user.user)
    if field is None:
        raise HTTPException(status_code=404, detail={"code": "FIELD_NOT_FOUND", "message": "Agriculture field not found."})
    return field


def _zone_out(zone: AgricultureFieldZone) -> dict[str, Any]:
    return {"id": zone.id, "zone_type": zone.zone_type, "geometry": zone.geometry_json, "name": zone.name, "kind": zone.kind, "radius_m": zone.radius_m, "height_m": zone.height_m, "metadata": zone.metadata_json or {}, "revision": zone.revision, "created_at": zone.created_at}


@router.post("/fields", response_model=FieldContextOut, status_code=201)
async def create_agriculture_field(payload: FieldContextCreate, db: AsyncSession = Depends(get_db), user: OrgUser = Depends(require_mission_exec)):
    boundary = _boundary_payload(payload.boundary)
    polygon = _geometry(boundary, field_name="boundary")
    field = await field_service.create(db, user=user.user, name=payload.name, polygon=polygon, workflow_scope="agriculture")
    revision = AgricultureFieldBoundaryRevision(field_id=field.id, org_id=user.org_id, created_by_user_id=user.user.id, revision=1, boundary_json=boundary, area_ha=_area_ha(polygon))
    db.add(revision)
    await db.commit()
    return await get_agriculture_field_context(field.id, db, user)


@router.get("/fields/{field_id}/boundary-context", response_model=FieldContextOut)
async def get_agriculture_field_context(field_id: int, db: AsyncSession = Depends(get_db), user: OrgUser = Depends(require_org_user)):
    field = await _owned(field_id, user, db)
    revisions = list((await db.scalars(select(AgricultureFieldBoundaryRevision).where(AgricultureFieldBoundaryRevision.field_id == field_id).order_by(AgricultureFieldBoundaryRevision.revision.desc()))).all())
    zones = list((await db.scalars(select(AgricultureFieldZone).where(AgricultureFieldZone.field_id == field_id).order_by(AgricultureFieldZone.created_at))).all())
    boundary = revisions[0].boundary_json if revisions else {"type": "Polygon", "coordinates": []}
    revision_rows = [{"revision": row.revision, "boundary": row.boundary_json, "area_ha": row.area_ha, "created_at": row.created_at} for row in revisions]
    return {"field_id": field.id, "name": field.name, "area_ha": field.area_ha, "boundary": boundary, "current_revision": revisions[0].revision if revisions else 0, "revisions": revision_rows, "zones": [_zone_out(zone) for zone in zones]}


@router.put("/fields/{field_id}/boundary", response_model=FieldContextOut)
async def update_agriculture_boundary(field_id: int, payload: BoundaryUpdate, db: AsyncSession = Depends(get_db), user: OrgUser = Depends(require_mission_exec)):
    field = await _owned(field_id, user, db)
    boundary = _boundary_payload(payload.boundary)
    polygon = _geometry(boundary, field_name="boundary")
    current = await db.scalar(select(AgricultureFieldBoundaryRevision).where(AgricultureFieldBoundaryRevision.field_id == field_id).order_by(AgricultureFieldBoundaryRevision.revision.desc()))
    next_revision = (current.revision if current else 0) + 1
    await field_service.update(db, field=field, name=None, polygon=polygon)
    db.add(AgricultureFieldBoundaryRevision(field_id=field_id, org_id=user.org_id, created_by_user_id=user.user.id, revision=next_revision, boundary_json={**boundary, "reason": payload.reason} if payload.reason else boundary, area_ha=_area_ha(polygon)))
    await db.commit()
    return await get_agriculture_field_context(field_id, db, user)


@router.post("/fields/{field_id}/zones", response_model=ZoneOut, status_code=201)
async def add_agriculture_zone(field_id: int, payload: ZoneIn, db: AsyncSession = Depends(get_db), user: OrgUser = Depends(require_mission_exec)):
    await _owned(field_id, user, db)
    boundary_row = await db.scalar(select(AgricultureFieldBoundaryRevision).where(AgricultureFieldBoundaryRevision.field_id == field_id).order_by(AgricultureFieldBoundaryRevision.revision.desc()))
    if boundary_row is None:
        raise HTTPException(status_code=409, detail={"code": "AGRICULTURE_BOUNDARY_REQUIRED", "message": "Save a boundary before adding zones."})
    boundary = _geometry(boundary_row.boundary_json, field_name="boundary")
    zone = _geometry(payload.geometry, field_name="zone.geometry")
    if not boundary.covers(zone):
        raise HTTPException(status_code=422, detail={"code": "AGRICULTURE_ZONE_OUTSIDE_FIELD", "field": "geometry", "message": "Exclusions and obstacles must be inside the field boundary."})
    row = AgricultureFieldZone(id=new_id(), field_id=field_id, org_id=user.org_id, created_by_user_id=user.user.id, revision=boundary_row.revision, zone_type=payload.zone_type, geometry_json=payload.geometry, name=payload.name, kind=payload.kind, radius_m=payload.radius_m, height_m=payload.height_m, metadata_json=payload.metadata)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _zone_out(row)


@router.delete("/fields/{field_id}/zones/{zone_id}", status_code=204)
async def delete_agriculture_zone(field_id: int, zone_id: str, db: AsyncSession = Depends(get_db), user: OrgUser = Depends(require_mission_exec)):
    await _owned(field_id, user, db)
    row = await db.scalar(select(AgricultureFieldZone).where(AgricultureFieldZone.id == zone_id, AgricultureFieldZone.field_id == field_id))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "AGRICULTURE_ZONE_NOT_FOUND", "message": "Zone not found."})
    await db.delete(row)
    await db.commit()
