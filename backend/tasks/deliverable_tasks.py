"""Celery tasks for generating FieldDeliverable files.

Task name  : backend.tasks.deliverable_tasks.generate_field_deliverable
Queue      : exports
Retries    : 3

Supported deliverable types:
  - GEOJSON       : GeoJSON FeatureCollection from field boundary (PostGIS ST_AsGeoJSON)
  - KML           : KML Placemark wrapping field name and area
  - HTML_SUMMARY  : Single-page HTML report (print-to-PDF friendly)
  - QA_CHECKLIST  : JSON checklist for post-flight quality assurance

Storage:
  - S3 backend  : upload to orgs/{org_id}/deliverables/{id}/{filename}
  - Local       : write to backend/storage/deliverables/{id}/{filename}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile

from backend.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    queue="exports",
    bind=True,
    max_retries=3,
    name="backend.tasks.deliverable_tasks.generate_field_deliverable",
)
def generate_field_deliverable(self, deliverable_id: int) -> None:
    """Synchronous Celery task entry-point — delegates to async implementation."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_generate(deliverable_id))
    except Exception as exc:
        logger.exception("Deliverable task failed for id=%s: %s", deliverable_id, exc)
        raise self.retry(exc=exc, countdown=30) from exc
    finally:
        loop.close()


async def _generate(deliverable_id: int) -> None:
    from sqlalchemy import text, update

    from backend.config import settings
    from backend.db.models import Field, FieldDeliverable
    from backend.db.session import Session

    async with Session() as db:
        # Mark running
        await db.execute(
            update(FieldDeliverable)
            .where(FieldDeliverable.id == deliverable_id)
            .values(status="processing")
        )
        await db.commit()

        try:
            d = await db.get(FieldDeliverable, deliverable_id)
            if not d:
                raise ValueError(f"FieldDeliverable {deliverable_id} not found")

            field = await db.get(Field, d.field_id)
            if not field:
                raise ValueError(f"Field {d.field_id} not found")

            content: bytes
            filename: str

            if d.type == "GEOJSON":
                result = await db.execute(
                    text("SELECT ST_AsGeoJSON(boundary)::json FROM fields WHERE id = :id"),
                    {"id": field.id},
                )
                geom = result.scalar()
                if geom is None:
                    raise ValueError(f"Field {field.id} has no boundary geometry")
                content = json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": geom,
                                "properties": {
                                    "id": field.id,
                                    "name": field.name,
                                    "area_ha": field.area_ha,
                                },
                            }
                        ],
                    }
                ).encode()
                filename = f"field_{field.id}.geojson"

            elif d.type == "KML":
                content = _build_kml(field).encode()
                filename = f"field_{field.id}.kml"

            elif d.type == "HTML_SUMMARY":
                content = _build_html_summary(field).encode()
                filename = f"field_{field.id}_summary.html"

            elif d.type == "QA_CHECKLIST":
                content = json.dumps(_build_qa_checklist(field)).encode()
                filename = f"field_{field.id}_qa.json"

            else:
                raise ValueError(f"Unknown deliverable type: {d.type!r}")

            # Upload or save
            if settings.storage_backend == "s3":
                from pathlib import Path

                from backend.services.storage.s3_client import ObjectStorageClient

                client = ObjectStorageClient()
                key = f"orgs/{d.org_id}/deliverables/{deliverable_id}/{filename}"
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=Path(filename).suffix
                ) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    await client.upload_file(Path(tmp_path), key)
                    d.url = key
                finally:
                    os.unlink(tmp_path)
            else:
                from pathlib import Path

                storage_dir = (
                    Path("backend") / "storage" / "deliverables" / str(deliverable_id)
                )
                storage_dir.mkdir(parents=True, exist_ok=True)
                out_path = storage_dir / filename
                out_path.write_bytes(content)
                d.url = str(out_path)

            d.status = "ready"
            d.error = None
            await db.commit()
            logger.info("Deliverable %s generated successfully: %s", deliverable_id, d.url)

        except Exception as exc:
            logger.exception("Deliverable generation failed for id=%s", deliverable_id)
            try:
                await db.execute(
                    update(FieldDeliverable)
                    .where(FieldDeliverable.id == deliverable_id)
                    .values(status="failed", error=str(exc)[:512])
                )
                await db.commit()
            except Exception:
                logger.exception(
                    "Could not persist failure status for deliverable %s", deliverable_id
                )
            raise


def _build_kml(field) -> str:
    name = field.name or f"Field {field.id}"
    area_str = f"{field.area_ha} ha" if field.area_ha is not None else "N/A"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Placemark>\n"
        f"    <name>{name}</name>\n"
        f"    <description>Area: {area_str}</description>\n"
        "  </Placemark>\n"
        "</kml>"
    )


def _build_html_summary(field) -> str:
    name = field.name or f"Field {field.id}"
    area_str = f"{field.area_ha} ha" if field.area_ha is not None else "N/A"
    return (
        "<!DOCTYPE html>"
        "<html>"
        f"<head><meta charset='utf-8'><title>Field Summary — {name}</title>"
        "<style>body{font-family:sans-serif;max-width:700px;margin:40px auto}"
        "table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:8px 12px;text-align:left}"
        "th{background:#f5f5f5}</style></head>"
        "<body>"
        f"<h1>Field Summary: {name}</h1>"
        "<table>"
        f"<tr><th>Field ID</th><td>{field.id}</td></tr>"
        f"<tr><th>Name</th><td>{name}</td></tr>"
        f"<tr><th>Area</th><td>{area_str}</td></tr>"
        "</table>"
        "<p><em>Print this page to PDF using your browser print function.</em></p>"
        "</body></html>"
    )


def _build_qa_checklist(field) -> dict:
    return {
        "field_id": field.id,
        "field_name": field.name,
        "area_ha": field.area_ha,
        "checklist": [
            {"item": "Boundary polygon verified", "status": "pending"},
            {"item": "GSD meets requirements (<3cm)", "status": "pending"},
            {"item": "Ortho coverage complete", "status": "pending"},
            {"item": "Elevation model reviewed", "status": "pending"},
        ],
    }
