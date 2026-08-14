export type AgricultureFieldProfile = {
  id: number;
  field_id: number;
  crop_type: string | null;
  variety: string | null;
  season: string | null;
  planting_date: string | null;
  growth_stage: string | null;
  row_direction_deg: number | null;
  expected_row_spacing_m: number | null;
  expected_plant_spacing_m?: number | null;
  stand_gap_multiplier?: number;
  weed_density_cell_m?: number;
  weed_hotspot_percentile?: number;
  soil_type: string | null;
  irrigation_method: string | null;
  management_zone: string | null;
  timezone: string;
  notes: string | null;
  metadata: Record<string, unknown>;
};

export type AgricultureFieldZone = {
  id: string;
  zone_type: "exclusion" | "obstacle";
  geometry: Record<string, unknown>;
  name: string;
  kind: string;
  radius_m: number | null;
  height_m: number | null;
  metadata: Record<string, unknown>;
  revision: number;
  created_at: string;
};

export type AgricultureBoundaryRevision = {
  revision: number;
  boundary: Record<string, unknown>;
  area_ha: number;
  created_at: string;
};

export type AgricultureFieldContext = {
  field_id: number;
  name: string;
  area_ha: number | null;
  boundary: { type: "Polygon"; coordinates: number[][][] };
  current_revision: number;
  revisions: AgricultureBoundaryRevision[];
  zones: AgricultureFieldZone[];
};

export type AgriculturePlanPreview = {
  field_id: number | null;
  area_m2: number;
  area_ha: number;
  footprint_width_m: number;
  footprint_height_m: number;
  estimated_gsd_cm: number;
  coverage_pct: number;
  estimated_duration_s: number | null;
  estimated_image_count: number | null;
  warnings: string[];
};

export type AgricultureFieldOverview = {
  id: number;
  name: string;
  area_ha: number | null;
  workflow_scope: string | null;
  geometry_geojson: Record<string, unknown>;
  profile: {
    crop_type?: string | null;
    variety?: string | null;
    season?: string | null;
    growth_stage?: string | null;
  };
  latest_flight: {
    id: string;
    status: string;
    created_at: string;
    quality_summary: Record<string, unknown>;
    coverage_summary: Record<string, unknown>;
  } | null;
};
