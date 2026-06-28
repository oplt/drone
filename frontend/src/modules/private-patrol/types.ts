import type { MissionLifecycleSlice, PreflightRunResponse } from "../mission-runtime";
import type { Waypoint } from "../mission-workflow";

export type PrivatePatrolMissionTaskType =
  | "perimeter_patrol"
  | "waypoint_patrol"
  | "grid_surveillance";

/** Includes API-only task type for event-response missions. */
export type PrivatePatrolTaskType =
  | PrivatePatrolMissionTaskType
  | "event_triggered_patrol";


export type PatrolAiTask =
  | "intruder_detection"
  | "vehicle_detection"
  | "fence_breach_detection"
  | "motion_detection";

export type PatrolPreviewStats = {
  task_type?: string;
  response_mode?: "incident_response" | "detection_search";
  waypoints?: number;
  key_points?: number;
  rows?: number;
  perimeter_m?: number;
  total_route_m?: number;
  area_m2?: number;
  path_offset_requested_m?: number;
  path_offset_applied_m?: number;
  grid_spacing_m?: number;
  grid_angle_deg?: number;
  patrol_loops?: number;
  hover_time_s?: number;
  hover_total_s?: number;
  verification_loiter_s?: number;
  estimated_duration_s?: number;
};

export type PatrolGridParams = {
  task_type: PrivatePatrolMissionTaskType;
  event_triggered_enabled: boolean;
  path_offset_m: number;
  direction: "clockwise" | "counterclockwise";
  patrol_loops: number;
  speed_mps: number;
  start_after_minutes: number;
  repeat_interval_minutes: number;
  camera_angle_deg: number;
  camera_overlap_pct: number;
  max_segment_length_m: number;
  hover_time_s: number;
  camera_scan_yaw_deg: number;
  zoom_capture: boolean;
  return_to_start: boolean;
  grid_spacing_m: number;
  grid_angle_deg: number;
  grid_pattern_mode: "boustrophedon" | "crosshatch";
  grid_crosshatch_angle_offset_deg: number;
  grid_lane_strategy: "serpentine" | "one_way";
  grid_start_corner: "auto" | "nw" | "ne" | "sw" | "se";
  grid_row_stride: number;
  grid_row_phase_m: number;
  safety_inset_m: number;
  verification_loiter_s: number;
  verification_radius_m: number;
  track_target: boolean;
  target_label: string;
  ai_tasks: PatrolAiTask[];
};

export interface PrivatePatrolMissionStatus {
  flight_id?: string;
  mission_name?: string;
  mission_lifecycle?: MissionLifecycleSlice | null;
  telemetry?: {
    running: boolean;
    active_connections?: number;
    has_position_data?: boolean;
    position?: {
      lat?: number;
      lon?: number;
      lng?: number;
      alt?: number;
      relative_alt?: number;
    };
  };
  orchestrator?: {
    drone_connected: boolean;
  };
}

export type NoticeSeverity = "success" | "info" | "warning" | "error";

export type UiNotice = {
  open: boolean;
  severity: NoticeSeverity;
  message: string;
};

export type { Waypoint, PreflightRunResponse };

export const DEFAULT_PATROL_GRID_PARAMS: PatrolGridParams = {
  task_type: "perimeter_patrol",
  event_triggered_enabled: false,
  path_offset_m: 15,
  direction: "clockwise",
  patrol_loops: 1,
  speed_mps: 6,
  start_after_minutes: 0,
  repeat_interval_minutes: 0,
  camera_angle_deg: 35,
  camera_overlap_pct: 50,
  max_segment_length_m: 20,
  hover_time_s: 15,
  camera_scan_yaw_deg: 360,
  zoom_capture: true,
  return_to_start: true,
  grid_spacing_m: 40,
  grid_angle_deg: 0,
  grid_pattern_mode: "boustrophedon",
  grid_crosshatch_angle_offset_deg: 90,
  grid_lane_strategy: "serpentine",
  grid_start_corner: "auto",
  grid_row_stride: 1,
  grid_row_phase_m: 0,
  safety_inset_m: 2,
  verification_loiter_s: 45,
  verification_radius_m: 18,
  track_target: true,
  target_label: "",
  ai_tasks: [
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
  ],
};

/** Repeat interval when armed; falls back to start delay when Repeat is 0. */
export function effectivePatrolRepeatIntervalMinutes(
  params: Pick<PatrolGridParams, "repeat_interval_minutes" | "start_after_minutes">,
): number {
  const repeat = Math.max(0, Math.min(1440, Math.round(params.repeat_interval_minutes)));
  if (repeat > 0) return repeat;
  const startDelay = Math.max(0, Math.min(1440, Math.round(params.start_after_minutes)));
  return startDelay > 0 ? startDelay : 0;
}
