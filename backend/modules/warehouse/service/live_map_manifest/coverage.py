"""Live-map flight manifest — rack-face coverage aggregation."""

from __future__ import annotations

import math
from typing import Any

from .coercion import _safe_float, _safe_int


def build_rack_face_coverage(
    chunk_quality: list[dict[str, Any]],
    *,
    min_points_per_m2: float = 15.0,
    max_viewing_angle_deg: float = 65.0,
    require_rgb: bool = False,
    require_esdf: bool = True,
) -> dict[str, Any]:
    """Aggregate chunk sidecars into operator-facing rack-face coverage bins."""
    faces: dict[str, dict[str, Any]] = {}
    global_esdf = any(str(item.get("source")) == "nvblox_esdf" for item in chunk_quality)
    for item in chunk_quality:
        face_id = item.get("rack_face_id")
        if not face_id:
            continue
        key = str(face_id)
        face = faces.setdefault(
            key,
            {
                "rack_face_id": key,
                "point_count": 0,
                "chunk_count": 0,
                "rgb_available": False,
                "esdf_available": False,
                "sources": [],
                "viewing_angles_deg": [],
            },
        )
        face["chunk_count"] = int(face["chunk_count"]) + 1
        face["point_count"] = int(face["point_count"]) + max(
            0, _safe_int(item.get("point_count"), 0)
        )
        source = str(item.get("source") or "unknown")
        if source not in face["sources"]:
            face["sources"].append(source)
        if bool(item.get("has_rgb")):
            face["rgb_available"] = True
        if source in {"nvblox_esdf", "nvblox_occupancy"}:
            face["esdf_available"] = True
        if item.get("rack_face_center_m") and "center_m" not in face:
            face["center_m"] = list(item["rack_face_center_m"])
        if item.get("rack_face_normal") and "normal" not in face:
            face["normal"] = list(item["rack_face_normal"])
        angle = item.get("viewing_angle_deg", item.get("incidence_angle_deg"))
        if angle is not None:
            face["viewing_angles_deg"].append(round(_safe_float(angle), 3))
        bbox = item.get("bbox_local_m")
        if isinstance(bbox, list) and len(bbox) == 6:
            current = face.get("bbox_local_m")
            if not isinstance(current, list) or len(current) != 6:
                face["bbox_local_m"] = list(bbox)
            else:
                face["bbox_local_m"] = [
                    min(float(current[0]), float(bbox[0])),
                    min(float(current[1]), float(bbox[1])),
                    min(float(current[2]), float(bbox[2])),
                    max(float(current[3]), float(bbox[3])),
                    max(float(current[4]), float(bbox[4])),
                    max(float(current[5]), float(bbox[5])),
                ]

    face_rows: list[dict[str, Any]] = []
    for face in faces.values():
        bbox = face.get("bbox_local_m")
        if isinstance(bbox, list) and len(bbox) == 6:
            area = max(0.0, abs(float(bbox[3]) - float(bbox[0]))) * max(
                0.0, abs(float(bbox[5]) - float(bbox[2]))
            )
        else:
            area = 0.0
        points_per_m2 = float(face["point_count"]) / area if area > 0 else 0.0
        angles = face.get("viewing_angles_deg")
        best_angle = min(float(v) for v in angles) if angles else None
        reasons: list[str] = []
        if points_per_m2 < float(min_points_per_m2):
            reasons.append("low_point_density")
        if best_angle is not None and best_angle > float(max_viewing_angle_deg):
            reasons.append("poor_viewing_angle")
        if require_rgb and not bool(face.get("rgb_available")):
            reasons.append("missing_rgb")
        if require_esdf and not (bool(face.get("esdf_available")) or global_esdf):
            reasons.append("missing_esdf")
        face_rows.append(
            {
                **face,
                "floor_area_m2": round(area, 3),
                "points_per_m2": round(points_per_m2, 3),
                "best_viewing_angle_deg": round(best_angle, 3) if best_angle is not None else None,
                "status": "covered" if not reasons else "uncovered",
                "reasons": reasons,
            }
        )
    face_rows.sort(key=lambda item: str(item.get("rack_face_id")))
    covered = sum(1 for item in face_rows if item["status"] == "covered")
    return {
        "faces": face_rows,
        "face_count": len(face_rows),
        "covered_face_count": covered,
        "uncovered_face_count": len(face_rows) - covered,
        "coverage_ratio": round(covered / len(face_rows), 3) if face_rows else None,
        "thresholds": {
            "min_points_per_m2": float(min_points_per_m2),
            "max_viewing_angle_deg": float(max_viewing_angle_deg),
            "require_rgb": bool(require_rgb),
            "require_esdf": bool(require_esdf),
        },
    }


def build_coverage_repair_waypoints(
    rack_face_coverage: dict[str, Any],
    *,
    standoff_m: float = 1.2,
) -> dict[str, Any]:
    waypoints: list[dict[str, Any]] = []
    faces = rack_face_coverage.get("faces") if isinstance(rack_face_coverage, dict) else []
    for face in faces if isinstance(faces, list) else []:
        if not isinstance(face, dict) or face.get("status") == "covered":
            continue
        center = face.get("center_m")
        normal = face.get("normal")
        if not (
            isinstance(center, list)
            and len(center) >= 3
            and isinstance(normal, list)
            and len(normal) >= 2
        ):
            continue
        nx, ny = _safe_float(normal[0]), _safe_float(normal[1])
        length = max((nx * nx + ny * ny) ** 0.5, 1e-6)
        nx, ny = nx / length, ny / length
        x = _safe_float(center[0]) + nx * float(standoff_m)
        y = _safe_float(center[1]) + ny * float(standoff_m)
        waypoints.append(
            {
                "rack_face_id": str(face.get("rack_face_id")),
                "pose_local_m": {
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "z": round(_safe_float(center[2], 1.5), 3),
                    "yaw_deg": round(math.degrees(math.atan2(-ny, -nx)), 2),
                    "frame_id": "warehouse_map",
                },
                "reasons": list(face.get("reasons") or []),
            }
        )
    return {
        "uncovered_rack_faces": [
            str(face.get("rack_face_id"))
            for face in faces
            if isinstance(face, dict) and face.get("status") == "uncovered"
        ]
        if isinstance(faces, list)
        else [],
        "extra_pass_waypoints": waypoints,
        "waypoint_count": len(waypoints),
    }


__all__ = ["build_coverage_repair_waypoints", "build_rack_face_coverage"]
