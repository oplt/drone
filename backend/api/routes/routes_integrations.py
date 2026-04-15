"""Partner integration endpoints — GIS/FMIS data export.

Prefix  : /integrations
Auth    : require_org_user
Routes  :
  GET  /integrations/fields/{field_id}/geojson  → GeoJSON FeatureCollection
  GET  /integrations/fields/{field_id}/kml       → KML placemark
  GET  /integrations/missions/{mission_id}/gpx   → GPX track
  POST /integrations/fmis/push/{field_id}        → trigger webhook FMIS delivery
"""
from __future__ import annotations

import json
import logging
from textwrap import dedent

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, text

from backend.auth.deps import OrgUser, require_org_user
from backend.db.session import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])


async def _get_field(db, field_id: int, org_id: int | None):
    """Return a field row, raising 404 if missing."""
    from backend.db.models import Field  # local import to avoid circular

    row = await db.get(Field, field_id)
    if not row:
        raise HTTPException(status_code=404, detail="Field not found")
    if (
        org_id is not None
        and getattr(row, "org_id", None) is not None
        and row.org_id != org_id
    ):
        raise HTTPException(status_code=403, detail="Not authorized")
    return row


@router.get("/fields/{field_id}/geojson")
async def field_geojson(
    field_id: int,
    org_user: OrgUser = Depends(require_org_user),
):
    """Return a GeoJSON FeatureCollection with the field boundary."""
    async with Session() as db:
        field = await _get_field(db, field_id, org_user.org_id)

        geojson_result = None
        if getattr(field, "boundary", None) is not None:
            row = await db.execute(
                text("SELECT ST_AsGeoJSON(ST_GeomFromEWKT(:geom))::json AS g"),
                {"geom": str(field.boundary)},
            )
            geojson_result = row.scalar_one_or_none()

        feature = {
            "type": "Feature",
            "properties": {
                "id": field.id,
                "name": getattr(field, "name", None),
                "area_ha": getattr(field, "area_ha", None),
                "crop_type": getattr(field, "crop_type", None),
            },
            "geometry": geojson_result,
        }
        collection = {"type": "FeatureCollection", "features": [feature]}

    return Response(
        content=json.dumps(collection),
        media_type="application/geo+json",
        headers={
            "Content-Disposition": f'attachment; filename="field_{field_id}.geojson"'
        },
    )


@router.get("/fields/{field_id}/kml")
async def field_kml(
    field_id: int,
    org_user: OrgUser = Depends(require_org_user),
):
    """Return a KML placemark with the field polygon."""
    async with Session() as db:
        field = await _get_field(db, field_id, org_user.org_id)

        kml_geom = ""
        if getattr(field, "boundary", None) is not None:
            row = await db.execute(
                text("SELECT ST_AsKML(ST_GeomFromEWKT(:geom)) AS k"),
                {"geom": str(field.boundary)},
            )
            kml_geom = row.scalar_one_or_none() or ""

        name = getattr(field, "name", None) or "Field"
        area_ha = getattr(field, "area_ha", None) or "?"
        crop_type = getattr(field, "crop_type", None) or "?"

    kml = dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
          <Document>
            <name>Field {field_id}</name>
            <Placemark>
              <name>{name}</name>
              <description>Area: {area_ha} ha | Crop: {crop_type}</description>
              {kml_geom}
            </Placemark>
          </Document>
        </kml>
    """)

    return Response(
        content=kml,
        media_type="application/vnd.google-earth.kml+xml",
        headers={
            "Content-Disposition": f'attachment; filename="field_{field_id}.kml"'
        },
    )


@router.get("/missions/{mission_id}/gpx")
async def mission_gpx(
    mission_id: int,
    org_user: OrgUser = Depends(require_org_user),
):
    """Return a GPX track from TelemetryRecords for the mission."""
    from backend.db.models import Flight, TelemetryRecord

    async with Session() as db:
        flight = await db.get(Flight, mission_id)
        if not flight:
            raise HTTPException(status_code=404, detail="Mission not found")
        if (
            org_user.org_id is not None
            and getattr(flight, "org_id", None) is not None
            and flight.org_id != org_user.org_id
        ):
            raise HTTPException(status_code=403, detail="Not authorized")

        stmt = (
            select(TelemetryRecord)
            .where(TelemetryRecord.flight_id == mission_id)
            .order_by(TelemetryRecord.timestamp)
            .limit(5000)
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

    track_points: list[str] = []
    for rec in records:
        lat = getattr(rec, "lat", None) or getattr(rec, "latitude", None)
        lon = getattr(rec, "lon", None) or getattr(rec, "longitude", None)
        alt = getattr(rec, "alt", None) or getattr(rec, "altitude", None)
        ts = getattr(rec, "timestamp", None)
        if lat is None or lon is None:
            continue
        time_str = f"<time>{ts}</time>" if ts else ""
        ele_str = f"<ele>{alt}</ele>" if alt is not None else ""
        track_points.append(
            f'    <trkpt lat="{lat}" lon="{lon}">{ele_str}{time_str}</trkpt>'
        )

    gpx = dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <gpx version="1.1" creator="DroneApp"
          xmlns="http://www.topografix.com/GPX/1/1">
          <trk>
            <name>Mission {mission_id}</name>
            <trkseg>
        {chr(10).join(track_points)}
            </trkseg>
          </trk>
        </gpx>
    """)

    return Response(
        content=gpx,
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": f'attachment; filename="mission_{mission_id}.gpx"'
        },
    )


@router.post("/fmis/push/{field_id}", status_code=202)
async def fmis_push(
    field_id: int,
    org_user: OrgUser = Depends(require_org_user),
):
    """Trigger webhook delivery of field data to FMIS subscribers."""
    from backend.services.webhooks import dispatch_event

    async with Session() as db:
        field = await _get_field(db, field_id, org_user.org_id)

        await dispatch_event(
            db=db,
            org_id=org_user.org_id,
            event_type="fmis.field_update",
            payload={
                "field_id": field.id,
                "name": getattr(field, "name", None),
                "area_ha": getattr(field, "area_ha", None),
                "crop_type": getattr(field, "crop_type", None),
            },
        )

    return {"queued": True, "field_id": field_id}
