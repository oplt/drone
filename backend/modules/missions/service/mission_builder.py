from __future__ import annotations

import math
from typing import Any, Literal

from backend.modules.missions.flight_profile import (
    FlightProfile,
    flight_profile_for_environment,
    flight_profile_for_mission_type,
)
from backend.modules.missions.planning.controlled_flight import ControlledFlightMission
from backend.modules.missions.planning.grid import GridMission
from backend.modules.missions.planning.photogrammetry import (
    PhotogrammetryMission as FlightPhotogrammetryMission,
)
from backend.modules.missions.planning.waypoint import WaypointsMission
from backend.modules.missions.schemas.mission_create import (
    MissionCreateIn,
    MissionProfileTriggerDistance,
    PhotogrammetryMissionProfile,
)
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.patrol.planning import (
    EventTriggeredPatrolMission,
    GridSurveillanceMission,
    PrivatePatrolMission,
    WaypointPatrolMission,
    normalize_ai_tasks,
    normalize_patrol_direction,
    normalize_trigger_type,
)
from backend.modules.vehicle_runtime.types import Coordinate


def flight_profile_for_payload(payload: MissionCreateIn | None) -> FlightProfile:
    if payload is None:
        return flight_profile_for_mission_type(None)
    if payload.flight_environment is not None:
        return flight_profile_for_environment(payload.flight_environment)
    return flight_profile_for_mission_type(payload.mission_type)
def _polygon_centroid_lonlat(
    polygon_lonlat: list[tuple[float, float]],
) -> tuple[float, float]:
    if len(polygon_lonlat) < 3:
        raise ValueError("polygon must have at least 3 points")
    pts = list(polygon_lonlat)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    lon = sum(float(p[0]) for p in pts) / len(pts)
    lat = sum(float(p[1]) for p in pts) / len(pts)
    return lon, lat


def _resolve_trigger_event_location(
    *,
    trigger_type: str,
    trigger_event_location_lonlat: list[float] | None,
    property_polygon_lonlat: list[list[float]] | None,
) -> tuple[float, float]:
    normalized_trigger = normalize_trigger_type(trigger_type)
    if trigger_event_location_lonlat and len(trigger_event_location_lonlat) >= 2:
        lon = float(trigger_event_location_lonlat[0])
        lat = float(trigger_event_location_lonlat[1])
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("trigger_event_location_lonlat must be valid [lon, lat]")
        return lon, lat

    if normalized_trigger == "night_schedule":
        polygon = [tuple(pt) for pt in (property_polygon_lonlat or [])]
        if len(polygon) >= 3:
            return _polygon_centroid_lonlat(polygon)

    raise ValueError(
        "Unable to resolve event location. Provide trigger_event_location_lonlat "
        "or property_polygon_lonlat for night_schedule."
    )
def build_mission(payload: MissionCreateIn, *, owner_id: int | None = None) -> Any:
    """Return the appropriate mission object for the given payload."""
    if payload.mission_type == MissionType.CONTROLLED:
        mission = ControlledFlightMission(cruise_alt=float(payload.cruise_alt))
        return mission, 0

    if payload.mission_type == MissionType.WAYPOINT:
        coords = [
            Coordinate(
                lat=w.lat,
                lon=w.lon,
                alt=payload.cruise_alt if w.alt is None else w.alt,
            )
            for w in payload.waypoints  # validated non-None by model_validator
        ]
        return WaypointsMission(waypoints=coords), len(coords)

    if payload.mission_type in {MissionType.GRID, MissionType.PHOTOGRAMMETRY}:
        g = payload.grid  # validated non-None by model_validator
        profile = payload.mission_profile
        if payload.mission_type == MissionType.PHOTOGRAMMETRY and profile is None:
            profile = PhotogrammetryMissionProfile()

        cruise_alt_m = payload.cruise_alt
        row_spacing_m = g.row_spacing_m
        agl_m = g.agl_m
        if profile is not None:
            recommended = _compute_photogrammetry_spacing(profile)
            cruise_alt_m = float(profile.altitude_m)
            agl_m = float(profile.altitude_m)
            row_spacing_m = recommended["cross_track_m"]

            # If trigger strategy under-samples along-track spacing, reject early.
            if recommended["effective_trigger_spacing_m"] > recommended["along_track_m"] * 1.15:
                raise ValueError(
                    "Trigger cadence is too sparse for requested front overlap. "
                    "Reduce trigger distance/interval or speed."
                )

        # Convert [[lon, lat], …] → [(lon, lat), …] tuples for GridMission.
        poly = [tuple(pt) for pt in g.field_polygon_lonlat]
        if profile is not None:
            trigger = profile.trigger
            trigger_mode: Literal["distance", "time"]
            trigger_distance_m = 0.0
            trigger_interval_s = 0.0
            if isinstance(trigger, MissionProfileTriggerDistance):
                trigger_mode = "distance"
                trigger_distance_m = float(trigger.distance_m)
            else:
                trigger_mode = "time"
                trigger_interval_s = float(trigger.interval_s)

            mission = FlightPhotogrammetryMission(
                polygon_lonlat=poly,
                altitude_agl=float(profile.altitude_m),
                fov_h=float(profile.camera.fov_h_deg),
                fov_v=float(profile.camera.fov_v_deg),
                front_overlap=float(profile.front_overlap_pct) / 100.0,
                side_overlap=float(profile.side_overlap_pct) / 100.0,
                min_spacing_m=float(profile.min_spacing_m),
                heading_deg=float(g.grid_angle_deg or 0.0),
                speed_mps=float(profile.speed_mps),
                trigger_mode=trigger_mode,
                trigger_distance_m=trigger_distance_m
                or max(float(profile.min_spacing_m), recommended["along_track_m"]),
                trigger_interval_s=trigger_interval_s
                or max(
                    0.2,
                    recommended["along_track_m"] / max(0.1, float(profile.speed_mps)),
                ),
                terrain_follow=bool(g.terrain_follow),
                terrain_target_agl_m=float(agl_m) if g.terrain_follow else None,
            )
            return mission, len(poly)

        mission = GridMission(
            cruise_alt_m=cruise_alt_m,
            field_polygon_lonlat=poly,
            row_spacing_m=row_spacing_m,
            grid_angle_deg=g.grid_angle_deg,
            slope_aware=g.slope_aware,
            safety_inset_m=g.safety_inset_m,
            terrain_follow=g.terrain_follow,
            agl_m=agl_m,
            pattern_mode=g.pattern_mode,
            crosshatch_angle_offset_deg=g.crosshatch_angle_offset_deg,
            start_corner=g.start_corner,
            lane_strategy=g.lane_strategy,
            row_stride=g.row_stride,
            row_phase_m=g.row_phase_m,
        )
        return mission, len(poly)

    if payload.mission_type in {
        MissionType.WAREHOUSE_SCAN,
        MissionType.WAREHOUSE_INSPECTION,
        MissionType.INDOOR_EXPLORATION,
    }:
        if payload.mission_type == MissionType.WAREHOUSE_SCAN:
            scan = payload.warehouse_scan
            if scan is None:
                raise ValueError("mission_type='warehouse_scan' requires warehouse_scan params")
            from backend.modules.warehouse.planning.mission import (
                WarehouseScanMissionParams,
                build_warehouse_scan_mission,
            )

            scan_params = (
                scan
                if isinstance(scan, WarehouseScanMissionParams)
                else WarehouseScanMissionParams.model_validate(scan)
            )
            return build_warehouse_scan_mission(
                base_height_m=float(payload.cruise_alt),
                scan=scan_params,
                owner_id=owner_id,
            )
        if payload.mission_type == MissionType.WAREHOUSE_INSPECTION:
            raise ValueError(
                "mission_type='warehouse_inspection' must be created via "
                "POST /warehouse/inspection-missions so local scan poses and results are persisted."
            )
        exploration = payload.warehouse_scan
        if exploration is None:
            raise ValueError(
                "mission_type='indoor_exploration' requires warehouse_scan exploration params"
            )
        from backend.modules.warehouse.planning.exploration import (
            WarehouseExplorationMissionParams,
            build_unknown_warehouse_exploration_mission,
        )

        exploration_params = (
            exploration
            if isinstance(exploration, WarehouseExplorationMissionParams)
            else WarehouseExplorationMissionParams.model_validate(exploration)
        )
        return build_unknown_warehouse_exploration_mission(
            hover_alt_m=float(payload.cruise_alt),
            exploration=exploration_params,
            owner_id=owner_id,
        )

    if payload.mission_type in {
        MissionType.PERIMETER_PATROL,
        MissionType.PRIVATE_PATROL,
    }:
        patrol = payload.private_patrol  # validated non-None by model_validator
        ai_tasks = normalize_ai_tasks(patrol.ai_tasks)
        if patrol.task_type == "event_triggered_patrol":
            event_lon, event_lat = _resolve_trigger_event_location(
                trigger_type=patrol.trigger_type,
                trigger_event_location_lonlat=patrol.trigger_event_location_lonlat,
                property_polygon_lonlat=patrol.property_polygon_lonlat,
            )
            mission = EventTriggeredPatrolMission(
                trigger_type=normalize_trigger_type(patrol.trigger_type),
                event_location_lonlat=(float(event_lon), float(event_lat)),
                altitude_agl=float(payload.cruise_alt),
                speed_mps=float(patrol.speed_mps),
                verification_loiter_s=float(patrol.verification_loiter_s),
                verification_radius_m=float(patrol.verification_radius_m),
                track_target=bool(patrol.track_target),
                auto_stream_video=bool(patrol.auto_stream_video),
                record_video_stream=bool(patrol.record_video_stream),
                target_label=patrol.target_label,
                ai_tasks=ai_tasks,
            )
            return mission, len(mission.get_waypoints())

        if patrol.task_type == "grid_surveillance":
            polygon = [tuple(pt) for pt in (patrol.property_polygon_lonlat or [])]
            mission = GridSurveillanceMission(
                polygon_lonlat=polygon,
                altitude_agl=float(payload.cruise_alt),
                speed_mps=float(patrol.speed_mps),
                grid_spacing_m=float(patrol.grid_spacing_m),
                grid_angle_deg=float(patrol.grid_angle_deg),
                safety_inset_m=float(patrol.safety_inset_m),
                pattern_mode=patrol.grid_pattern_mode,
                crosshatch_angle_offset_deg=float(patrol.grid_crosshatch_angle_offset_deg),
                lane_strategy=patrol.grid_lane_strategy,
                start_corner=patrol.grid_start_corner,
                row_stride=int(patrol.grid_row_stride),
                row_phase_m=float(patrol.grid_row_phase_m),
                record_video_stream=bool(patrol.record_video_stream),
                ai_tasks=ai_tasks,
            )
            return mission, len(mission.get_waypoints())

        if patrol.task_type == "waypoint_patrol":
            key_points = [tuple(pt) for pt in (patrol.key_points_lonlat or [])]
            mission = WaypointPatrolMission(
                key_points_lonlat=key_points,
                altitude_agl=float(payload.cruise_alt),
                speed_mps=float(patrol.speed_mps),
                hover_time_s=float(patrol.hover_time_s),
                camera_scan_yaw_deg=float(patrol.camera_scan_yaw_deg),
                zoom_capture=bool(patrol.zoom_capture),
                return_to_start=bool(patrol.return_to_start),
                record_video_stream=bool(patrol.record_video_stream),
                ai_tasks=ai_tasks,
            )
            return mission, len(mission.get_waypoints())

        polygon = [tuple(pt) for pt in (patrol.property_polygon_lonlat or [])]
        direction = normalize_patrol_direction(patrol.direction)
        mission = PrivatePatrolMission(
            polygon_lonlat=polygon,
            altitude_agl=float(payload.cruise_alt),
            speed_mps=float(patrol.speed_mps),
            patrol_direction=direction,
            path_offset_m=float(patrol.path_offset_m),
            loop_count=int(patrol.patrol_loops),
            camera_angle_deg=float(patrol.camera_angle_deg),
            camera_overlap_pct=float(patrol.camera_overlap_pct),
            max_segment_length_m=float(patrol.max_segment_length_m),
            record_video_stream=bool(patrol.record_video_stream),
            ai_tasks=ai_tasks,
        )
        return mission, len(mission.get_waypoints())

    raise ValueError(f"Unknown mission_type: {payload.mission_type!r}")


def _compute_photogrammetry_spacing(profile: PhotogrammetryMissionProfile) -> dict:
    """Derive survey spacing from capture profile."""
    front = float(profile.front_overlap_pct) / 100.0
    side = float(profile.side_overlap_pct) / 100.0
    altitude = float(profile.altitude_m)

    footprint_w = 2.0 * altitude * math.tan(math.radians(profile.camera.fov_h_deg / 2.0))
    footprint_h = 2.0 * altitude * math.tan(math.radians(profile.camera.fov_v_deg / 2.0))

    spacing_floor = max(0.0, float(profile.min_spacing_m))
    along_track_m = max(spacing_floor, footprint_h * (1.0 - front))
    cross_track_m = max(spacing_floor, footprint_w * (1.0 - side))

    trigger = profile.trigger
    if isinstance(trigger, MissionProfileTriggerDistance):
        effective_trigger_spacing = float(trigger.distance_m)
    else:
        effective_trigger_spacing = float(profile.speed_mps) * float(trigger.interval_s)

    return {
        "along_track_m": along_track_m,
        "cross_track_m": cross_track_m,
        "effective_trigger_spacing_m": effective_trigger_spacing,
    }
