"""Live-map flight manifest — chunk quality sidecar helpers."""

from __future__ import annotations

from typing import Any

from .coercion import _safe_float, _safe_int


def _point_from_sidecar(sidecar: dict[str, Any], key: str) -> list[float] | None:
    raw = sidecar.get(key)
    if isinstance(raw, dict):
        try:
            return [float(raw["x"]), float(raw["y"]), float(raw.get("z", 0.0))]
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(raw, list | tuple) and len(raw) >= 2:
        try:
            return [
                float(raw[0]),
                float(raw[1]),
                float(raw[2]) if len(raw) > 2 else 0.0,
            ]
        except (TypeError, ValueError):
            return None
    return None


def _normal_from_sidecar(sidecar: dict[str, Any]) -> list[float] | None:
    return _point_from_sidecar(sidecar, "rack_face_normal") or _point_from_sidecar(
        sidecar, "face_normal"
    )


def _chunk_quality_entry(
    *,
    chunk_id: str,
    source: str,
    stored_path: str,
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "chunk_id": chunk_id,
        "source": source,
        "path": stored_path,
        "point_count": max(0, _safe_int(sidecar.get("point_count"), 0)),
        "has_rgb": bool(sidecar.get("has_rgb")),
    }
    for key in ("source_topic", "frame_id", "encoding", "layer", "layer_type"):
        if sidecar.get(key):
            entry[key] = str(sidecar[key])
    bbox = sidecar.get("bbox_local_m")
    if isinstance(bbox, list) and len(bbox) == 6:
        try:
            entry["bbox_local_m"] = [round(float(v), 3) for v in bbox]
        except (TypeError, ValueError):
            pass
    face_id = sidecar.get("rack_face_id") or sidecar.get("face_id")
    if face_id:
        entry["rack_face_id"] = str(face_id)
    center = _point_from_sidecar(sidecar, "rack_face_center") or _point_from_sidecar(
        sidecar, "face_center"
    )
    if center is not None:
        entry["rack_face_center_m"] = [round(float(v), 3) for v in center]
    normal = _normal_from_sidecar(sidecar)
    if normal is not None:
        entry["rack_face_normal"] = [round(float(v), 4) for v in normal]
    for key in ("viewing_angle_deg", "incidence_angle_deg"):
        if sidecar.get(key) is not None:
            entry[key] = round(_safe_float(sidecar.get(key)), 3)
            break
    return entry


__all__ = ["_chunk_quality_entry", "_normal_from_sidecar", "_point_from_sidecar"]
