"""Pure P5 routing, export and agronomic-safety helpers."""

from __future__ import annotations

import csv
import io
import json
import struct
import zipfile
from datetime import UTC, datetime
from typing import Any

from shapely.geometry import shape
from backend.modules.agriculture.contracts_validation import validate_geojson


def _score(row: dict[str, Any]) -> float:
    return max(0.0, float(row.get("severity", 0))) * max(0.0, float(row.get("confidence", 0))) * max(1.0, float(row.get("area_m2") or 1.0) ** 0.5)


def plan_inspection_waypoints(candidates: list[dict[str, Any]], *, field_boundary: dict[str, Any], no_go_geometries: list[dict[str, Any]] | None = None, max_actions: int = 50, battery_budget_s: float | None = None, seconds_per_action: float = 90.0) -> dict[str, Any]:
    boundary = shape(field_boundary) if field_boundary else None; no_go = [shape(item) for item in (no_go_geometries or []) if item]
    eligible: list[dict[str, Any]] = []; rejected: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=_score, reverse=True):
        geometry = candidate.get("geometry_geojson") or {}
        try: point = shape(geometry).representative_point()
        except Exception: rejected.append({"source_id": candidate.get("id"), "reason": "invalid_geometry"}); continue
        if boundary is not None and not boundary.covers(point): rejected.append({"source_id": candidate.get("id"), "reason": "outside_field_boundary"}); continue
        if any(zone.covers(point) for zone in no_go): rejected.append({"source_id": candidate.get("id"), "reason": "inside_no_go_geometry"}); continue
        eligible.append({**candidate, "waypoint_geojson": {"type": "Point", "coordinates": [float(point.x), float(point.y)]}})
    budget_count = max_actions
    if battery_budget_s is not None: budget_count = min(budget_count, max(0, int(float(battery_budget_s) // max(1.0, seconds_per_action))))
    selected = eligible[:budget_count]
    rejected.extend({"source_id": row.get("id"), "reason": "battery_or_action_budget"} for row in eligible[budget_count:])
    for rank, row in enumerate(selected, 1): row["priority_rank"] = rank
    return {"status": "ready" if selected else "blocked", "actions": selected, "rejected": rejected, "constraints": {"max_actions": max_actions, "battery_budget_s": battery_budget_s, "seconds_per_action": seconds_per_action, "no_go_count": len(no_go), "policy": "confirmed evidence only; field boundary and battery constrained"}}


def _feature_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("features", []))


def build_geojson(payload: dict[str, Any]) -> bytes:
    validate_geojson(payload)
    return json.dumps(payload, sort_keys=True, default=str, indent=2).encode()


def build_csv(payload: dict[str, Any]) -> bytes:
    rows = _feature_rows(payload); output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=["id", "issue_type", "severity", "confidence", "status", "source_ids"]); writer.writeheader()
    for row in rows:
        props = row.get("properties", {}); writer.writerow({"id": props.get("id"), "issue_type": props.get("issue_type"), "severity": props.get("severity"), "confidence": props.get("confidence"), "status": props.get("status"), "source_ids": json.dumps(props.get("source_ids", []), sort_keys=True)})
    return output.getvalue().encode()


def _shape_parts(geometry: dict[str, Any]) -> tuple[int, list[list[list[float]]]]:
    kind = geometry.get("type"); coordinates = geometry.get("coordinates")
    if kind == "Point": return 1, [[[float(coordinates[0]), float(coordinates[1])]]]
    if kind == "Polygon": return 5, [[[float(point[0]), float(point[1])] for point in ring] for ring in (coordinates or [])]
    if kind == "MultiPolygon" and coordinates:
        rings = [[ [float(point[0]), float(point[1])] for point in ring] for polygon in coordinates for ring in polygon]
        return 5, rings
    return 0, []


def build_shapefile_zip(payload: dict[str, Any]) -> bytes:
    features = _feature_rows(payload); converted = [(feature, *_shape_parts(feature.get("geometry", {}))) for feature in features]; converted = [item for item in converted if item[1] in {1, 5}]
    shape_type = converted[0][1] if converted else 1; records: list[bytes] = []; boxes: list[tuple[float, float, float, float]] = []
    for feature, kind, parts in converted:
        if kind != shape_type: continue
        points = [point for ring in parts for point in ring]; bbox = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)); boxes.append(bbox)
        if kind == 1: content = struct.pack("<idd", 1, points[0][0], points[0][1])
        else:
            offsets=[]; flat=[]
            for ring in parts: offsets.append(len(flat)); flat.extend(ring)
            content = struct.pack("<i4d2i", 5, *bbox, len(offsets), len(flat)) + b"".join(struct.pack("<i", offset) for offset in offsets) + b"".join(struct.pack("<dd", *point) for point in flat)
        records.append(content)
    bbox = (min((item[0] for item in boxes), default=0), min((item[1] for item in boxes), default=0), max((item[2] for item in boxes), default=0), max((item[3] for item in boxes), default=0))
    def header(file_length_words: int) -> bytes:
        return struct.pack(">6i", 9994, 0, 0, 0, 0, 0) + struct.pack(">i", file_length_words) + struct.pack("<2i4d4d", 1000, shape_type, *bbox, 0, 0, 0, 0)
    shp_records=b"".join(struct.pack(">2i", index + 1, len(content)//2) + content for index, content in enumerate(records)); shp=header((100 + len(shp_records))//2)+shp_records; offsets=[]; cursor=50
    for content in records: offsets.append((cursor, len(content)//2)); cursor += 4 + len(content)//2
    shx=header((100 + len(offsets)*8)//2)+b"".join(struct.pack(">2i", *item) for item in offsets)
    fields=[("id", "C", 40, 0), ("issue_type", "C", 48, 0), ("severity", "N", 12, 4), ("confidence", "N", 12, 4), ("status", "C", 24, 0)]
    dbf=bytearray(struct.pack("<BBBBIHH20x", 3, datetime.now(UTC).year-2000, datetime.now(UTC).month, datetime.now(UTC).day, len(records), 32+32*len(fields)+1, 1+sum(field[2] for field in fields)))
    for name, kind, length, decimals in fields: dbf.extend(name.encode()[:10].ljust(11,b"\0") + kind.encode() + b"\0\0\0\0" + bytes([length, decimals]) + b"\0"*14)
    dbf.extend(b"\r")
    for feature, kind, parts in converted:
        if kind != shape_type: continue
        props=feature.get("properties", {}); dbf.extend(b" "); values=[str(props.get("id", "")), str(props.get("issue_type", "")), f"{float(props.get('severity', 0)):.4f}", f"{float(props.get('confidence', 0)):.4f}", str(props.get("status", ""))]
        for value, (_, kind, length, _) in zip(values, fields): dbf.extend(value.encode()[:length].rjust(length) if kind == "N" else value.encode()[:length].ljust(length))
    dbf.extend(b"\x1a")
    output=io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("agriculture.shp", shp); archive.writestr("agriculture.shx", shx); archive.writestr("agriculture.dbf", bytes(dbf)); archive.writestr("agriculture.prj", 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],AUTHORITY["EPSG","4326"]]')
    return output.getvalue()


def build_pdf(payload: dict[str, Any]) -> bytes:
    metadata = payload.get("metadata") or {}
    summary = metadata.get("summary") or {}
    by_type = summary.get("by_type") or {}
    lines = [
        f"Agriculture {metadata.get('template_key', 'field')} report",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Field: {metadata.get('field_id', '—')}  Flight: {metadata.get('flight_id', '—')}",
        f"Analysis run: {metadata.get('run_id', '—')}",
        f"Snapshot: {metadata.get('report_snapshot_id', 'live-query')}",
        f"Observations: {summary.get('observation_count', len(_feature_rows(payload)))}",
        f"Confirmed: {summary.get('confirmed_count', '—')}  Awaiting review: {summary.get('unreviewed_count', '—')}",
        "Findings by type: " + (", ".join(f"{key}={value}" for key, value in sorted(by_type.items())) or "none"),
        "",
        "This report contains observations and safety metadata; it is not treatment advice.",
    ]
    text="BT /F1 12 Tf 50 760 Td " + " ".join(f"({line.replace('(', '[').replace(')', ']')}) Tj 0 -18 Td" for line in lines) + " ET"; objects=[b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", f"<< /Length {len(text.encode())} >>\nstream\n{text}\nendstream".encode()]; output=bytearray(b"%PDF-1.4\n"); offsets=[]
    for index, obj in enumerate(objects, 1): offsets.append(len(output)); output.extend(f"{index} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=len(output); output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()); output.extend("".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()); output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()); return bytes(output)
