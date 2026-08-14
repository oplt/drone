from __future__ import annotations

import math
from itertools import pairwise

from backend.modules.missions.api.mission_route_schemas import (
    PrivatePatrolPreviewIn,
    PrivatePatrolPreviewOut,
)
from backend.modules.missions.service.mission_builder import _resolve_trigger_event_location
from backend.modules.patrol.planning import (
    estimate_camera_trigger_distance_m,
    generate_event_triggered_patrol_plan,
    generate_grid_surveillance_plan,
    generate_private_patrol_plan,
    generate_waypoint_patrol_plan,
    normalize_ai_tasks,
    normalize_patrol_direction,
    repeat_patrol_loops,
)


def _route_length_m(waypoints) -> float:
    total_route_m = 0.0
    if len(waypoints) < 2:
        return total_route_m
    for start, end in pairwise(waypoints):
        total_route_m += math.hypot(
            (float(end.lat) - float(start.lat)) * 111_132.0,
            (float(end.lon) - float(start.lon))
            * 111_320.0
            * math.cos(math.radians((float(start.lat) + float(end.lat)) / 2.0)),
        )
    return total_route_m


def _plan_waypoints(payload: PrivatePatrolPreviewIn):
    if payload.task_type == "event_triggered_patrol":
        resolved = _resolve_trigger_event_location(
            trigger_event_location_lonlat=payload.trigger_event_location_lonlat,
            property_polygon_lonlat=payload.property_polygon_lonlat,
        )
        if resolved is not None:
            plan = generate_event_triggered_patrol_plan(
                resolved,
                altitude_agl_m=float(payload.cruise_alt),
                verification_radius_m=float(payload.verification_radius_m),
                geofence_polygon_lonlat=[
                    tuple(point) for point in (payload.property_polygon_lonlat or [])
                ],
            )
        else:
            polygon = [tuple(point) for point in (payload.property_polygon_lonlat or [])]
            plan = generate_grid_surveillance_plan(
                polygon,
                altitude_agl_m=float(payload.cruise_alt),
                grid_spacing_m=float(payload.grid_spacing_m),
                grid_angle_deg=float(payload.grid_angle_deg),
                safety_inset_m=float(payload.safety_inset_m),
                pattern_mode=payload.grid_pattern_mode,
                crosshatch_angle_offset_deg=float(payload.grid_crosshatch_angle_offset_deg),
                lane_strategy=payload.grid_lane_strategy,
                start_corner=payload.grid_start_corner,
                row_stride=int(payload.grid_row_stride),
                row_phase_m=float(payload.grid_row_phase_m),
            )
        return plan, plan.waypoints

    if payload.task_type == "grid_surveillance":
        polygon = [tuple(point) for point in (payload.property_polygon_lonlat or [])]
        plan = generate_grid_surveillance_plan(
            polygon,
            altitude_agl_m=float(payload.cruise_alt),
            grid_spacing_m=float(payload.grid_spacing_m),
            grid_angle_deg=float(payload.grid_angle_deg),
            safety_inset_m=float(payload.safety_inset_m),
            pattern_mode=payload.grid_pattern_mode,
            crosshatch_angle_offset_deg=float(payload.grid_crosshatch_angle_offset_deg),
            lane_strategy=payload.grid_lane_strategy,
            start_corner=payload.grid_start_corner,
            row_stride=int(payload.grid_row_stride),
            row_phase_m=float(payload.grid_row_phase_m),
        )
        return plan, plan.waypoints

    if payload.task_type == "waypoint_patrol":
        key_points = [tuple(point) for point in (payload.key_points_lonlat or [])]
        plan = generate_waypoint_patrol_plan(
            key_points,
            altitude_agl_m=float(payload.cruise_alt),
            return_to_start=bool(payload.return_to_start),
        )
        return plan, plan.waypoints

    direction = normalize_patrol_direction(payload.direction)
    polygon = [tuple(point) for point in (payload.property_polygon_lonlat or [])]
    plan = generate_private_patrol_plan(
        polygon,
        altitude_agl_m=float(payload.cruise_alt),
        path_offset_m=float(payload.path_offset_m),
        direction=direction,
        max_segment_length_m=float(payload.max_segment_length_m),
    )
    return plan, repeat_patrol_loops(plan.waypoints, loops=int(payload.patrol_loops))


def build_private_patrol_preview(payload: PrivatePatrolPreviewIn) -> PrivatePatrolPreviewOut:
    ai_tasks = normalize_ai_tasks(payload.ai_tasks)
    plan, waypoints = _plan_waypoints(payload)
    total_route_m = _route_length_m(waypoints)
    mask_len = max(0, len(waypoints) - 1)
    waypoint_payload = [{"lat": waypoint.lat, "lon": waypoint.lon} for waypoint in waypoints]
    ai_task_labels = [str(task) for task in ai_tasks]

    if payload.task_type == "waypoint_patrol":
        key_points_count = len(payload.key_points_lonlat or [])
        hover_total_s = float(payload.hover_time_s) * float(key_points_count)
        est_duration_s = (total_route_m / max(0.1, float(payload.speed_mps))) + hover_total_s
        return PrivatePatrolPreviewOut(
            waypoints=waypoint_payload,
            work_leg_mask=[True] * mask_len,
            stats={
                **plan.stats,
                "task_type": payload.task_type,
                "key_points": key_points_count,
                "waypoints": len(waypoints),
                "hover_time_s": float(payload.hover_time_s),
                "hover_total_s": round(hover_total_s, 1),
                "total_route_m": round(total_route_m, 1),
                "estimated_duration_s": round(est_duration_s, 1),
                "speed_mps": float(payload.speed_mps),
            },
            camera={
                "scan_yaw_deg": float(payload.camera_scan_yaw_deg),
                "zoom_capture": bool(payload.zoom_capture),
            },
            ai_tasks=ai_task_labels,
        )

    if payload.task_type == "event_triggered_patrol":
        response_mode = (
            "incident_response"
            if payload.trigger_event_location_lonlat
            and len(payload.trigger_event_location_lonlat) == 2
            else "detection_search"
        )
        travel_s = total_route_m / max(0.1, float(payload.speed_mps))
        est_duration_s = travel_s + float(payload.verification_loiter_s)
        return PrivatePatrolPreviewOut(
            waypoints=waypoint_payload,
            work_leg_mask=[True] * mask_len,
            stats={
                **plan.stats,
                "task_type": payload.task_type,
                "response_mode": response_mode,
                "waypoints": len(waypoints),
                "total_route_m": round(total_route_m, 1),
                "estimated_duration_s": round(est_duration_s, 1),
                "verification_loiter_s": float(payload.verification_loiter_s),
                "speed_mps": float(payload.speed_mps),
            },
            camera={
                "stream_to_operator": bool(payload.auto_stream_video),
                "track_target": bool(payload.track_target),
                "target_label": payload.target_label,
            },
            ai_tasks=ai_task_labels,
        )

    if payload.task_type == "grid_surveillance":
        est_duration_s = total_route_m / max(0.1, float(payload.speed_mps))
        return PrivatePatrolPreviewOut(
            waypoints=waypoint_payload,
            work_leg_mask=[True] * mask_len,
            stats={
                **plan.stats,
                "task_type": payload.task_type,
                "waypoints": len(waypoints),
                "total_route_m": round(total_route_m, 1),
                "estimated_duration_s": round(est_duration_s, 1),
                "speed_mps": float(payload.speed_mps),
            },
            camera={
                "mode": "wide_coverage",
                "grid_spacing_m": float(payload.grid_spacing_m),
                "record_video_stream": bool(payload.record_video_stream),
            },
            ai_tasks=ai_task_labels,
        )

    est_duration_s = total_route_m / max(0.1, float(payload.speed_mps))
    trigger_distance_m = estimate_camera_trigger_distance_m(
        altitude_agl_m=float(payload.cruise_alt),
        overlap_pct=float(payload.camera_overlap_pct),
    )
    return PrivatePatrolPreviewOut(
        waypoints=waypoint_payload,
        work_leg_mask=[True] * mask_len,
        stats={
            **plan.stats,
            "task_type": payload.task_type,
            "patrol_loops": int(payload.patrol_loops),
            "waypoints": len(waypoints),
            "total_route_m": round(total_route_m, 1),
            "estimated_duration_s": round(est_duration_s, 1),
            "speed_mps": float(payload.speed_mps),
        },
        camera={
            "angle_deg": float(payload.camera_angle_deg),
            "overlap_pct": float(payload.camera_overlap_pct),
            "trigger_distance_m": round(trigger_distance_m, 2),
        },
        ai_tasks=ai_task_labels,
    )
