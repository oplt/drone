import { httpRequest } from "../../../shared/api/httpClient";

export type GeoPoint = { lat: number; lon: number; alt?: number | null };
export type GeoJsonPolygon = { type: "Polygon"; coordinates: number[][][] };

export type PropertyPatrolSite = {
  id: number;
  name: string;
  description?: string | null;
  property_boundary: GeoJsonPolygon;
  flight_safe_area: GeoJsonPolygon;
  no_fly_zones: GeoJsonPolygon[];
  privacy_zones: GeoJsonPolygon[];
  emergency_landing_zones: GeoJsonPolygon[];
  default_home_position?: GeoPoint | null;
  default_altitude_m: number;
  created_at: string;
  updated_at: string;
};

export type PatrolTemplate = {
  id: number;
  site_id: number;
  name: string;
  patrol_mode: "perimeter" | "grid" | "adaptive";
  altitude_m: number;
  speed_mps: number;
  boundary_offset_m: number;
  grid_spacing_m: number;
  overlap_percent: number;
  camera_direction: "inward" | "outward" | "forward" | "adaptive";
  camera_gimbal_pitch_deg: number;
  schedule_interval_minutes?: number | null;
  max_mission_duration_minutes: number;
  min_battery_return_percent: number;
  trigger_behavior: "notify_only" | "approval_required" | "auto_dispatch";
  ai_detection_enabled: boolean;
  llm_summary_enabled: boolean;
  privacy_blur_faces: boolean;
  privacy_blur_license_plates: boolean;
  event_clip_recording_only: boolean;
  retention_hours_or_days: string;
  created_at: string;
  updated_at: string;
};

export type PropertyPatrolWaypoint = {
  lat: number;
  lon: number;
  alt: number;
  speed_mps?: number;
  camera_direction?: string;
};

export type ValidationResult = {
  ok: boolean;
  errors: { code: string; message: string; waypoint_index?: number | null }[];
  warnings: { code: string; message: string; waypoint_index?: number | null }[];
};

export type RoutePreview = {
  waypoints: PropertyPatrolWaypoint[];
  stats: Record<string, unknown>;
  validation: ValidationResult;
};

export type PatrolIncident = {
  id: number;
  site_id: number;
  source: string;
  event_type: string;
  severity: string;
  confidence?: number | null;
  zone_id?: string | null;
  detected_objects: string[];
  llm_summary?: string | null;
  operator_notes?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export function listPropertyPatrolSites(token?: string | null) {
  return httpRequest<PropertyPatrolSite[]>("/api/property-patrol/sites", { token });
}

export function createPropertyPatrolSite(
  body: Omit<PropertyPatrolSite, "id" | "created_at" | "updated_at">,
  token?: string | null,
) {
  return httpRequest<PropertyPatrolSite>("/api/property-patrol/sites", {
    method: "POST",
    body,
    token,
  });
}

export function listPropertyPatrolTemplates(siteId?: number | null, token?: string | null) {
  const qs = siteId ? `?site_id=${siteId}` : "";
  return httpRequest<PatrolTemplate[]>(`/api/property-patrol/templates${qs}`, { token });
}

export function createPropertyPatrolTemplate(
  body: Omit<PatrolTemplate, "id" | "created_at" | "updated_at">,
  token?: string | null,
) {
  return httpRequest<PatrolTemplate>("/api/property-patrol/templates", {
    method: "POST",
    body,
    token,
  });
}

export function previewPropertyPatrolRoute(
  body: {
    site_id: number;
    template_id?: number | null;
    patrol_mode?: PatrolTemplate["patrol_mode"];
    altitude_m?: number;
    speed_mps?: number;
    boundary_offset_m?: number;
    grid_spacing_m?: number;
    camera_direction?: PatrolTemplate["camera_direction"];
  },
  token?: string | null,
) {
  return httpRequest<RoutePreview>("/api/property-patrol/route-preview", {
    method: "POST",
    body,
    token,
  });
}

export function startPropertyPatrolMission(
  body: { site_id: number; template_id?: number | null; mission_type: "manual" | "scheduled" | "sensor_triggered" },
  token?: string | null,
) {
  return httpRequest("/api/property-patrol/missions/start", {
    method: "POST",
    body,
    token,
  });
}

export function listPropertyPatrolIncidents(siteId?: number | null, token?: string | null) {
  const qs = siteId ? `?site_id=${siteId}` : "";
  return httpRequest<PatrolIncident[]>(`/api/property-patrol/incidents${qs}`, { token });
}

