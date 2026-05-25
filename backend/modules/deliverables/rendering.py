from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class RenderedDeliverable:
    filename: str
    content: bytes


def render_deliverable(deliverable_type: str, field, geometry: dict | None) -> RenderedDeliverable:
    if deliverable_type == "GEOJSON":
        if geometry is None:
            raise ValueError(f"Field {field.id} has no boundary geometry")
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {"id": field.id, "name": field.name, "area_ha": field.area_ha},
                }
            ],
        }
        return RenderedDeliverable(f"field_{field.id}.geojson", json.dumps(payload).encode())
    if deliverable_type == "KML":
        return RenderedDeliverable(f"field_{field.id}.kml", _kml(field).encode())
    if deliverable_type == "HTML_SUMMARY":
        return RenderedDeliverable(f"field_{field.id}_summary.html", _html(field).encode())
    if deliverable_type == "QA_CHECKLIST":
        return RenderedDeliverable(
            f"field_{field.id}_qa.json", json.dumps(_checklist(field)).encode()
        )
    raise ValueError(f"Unknown deliverable type: {deliverable_type!r}")


def _kml(field) -> str:
    name = escape(field.name or f"Field {field.id}")
    area = f"{field.area_ha} ha" if field.area_ha is not None else "N/A"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        f"  <Placemark><name>{name}</name><description>Area: {area}</description></Placemark>\n"
        "</kml>"
    )


def _html(field) -> str:
    name = escape(field.name or f"Field {field.id}")
    area = f"{field.area_ha} ha" if field.area_ha is not None else "N/A"
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Field Summary - {name}</title>"
        "<style>body{font-family:sans-serif;max-width:700px;margin:40px auto}"
        "table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:8px 12px;text-align:left}</style></head><body>"
        f"<h1>Field Summary: {name}</h1><table>"
        f"<tr><th>Field ID</th><td>{field.id}</td></tr>"
        f"<tr><th>Name</th><td>{name}</td></tr><tr><th>Area</th><td>{area}</td></tr>"
        "</table></body></html>"
    )


def _checklist(field) -> dict:
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
