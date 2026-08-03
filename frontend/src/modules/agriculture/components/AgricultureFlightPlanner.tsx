import { Alert, CircularProgress, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { startAgricultureFlight } from "../api";
import {
  useAcknowledgeAgriculturePreflight,
  useCreateAgriculturePlan,
  useEvaluateAgriculturePreflight,
  useAgricultureFieldContext,
  useUpdateAgriculturePlanGrid,
} from "../hooks";
import type { AgricultureFieldProfile, AgricultureMissionProfile } from "../types";
import { AgriculturePlannerForm, type AgriculturePlannerValues } from "./AgriculturePlannerForm";
import { AgricultureGridEditor } from "./AgricultureGridEditor";

const defaultProfile: AgricultureMissionProfile = {
  flight_kind: "agriculture_survey", preset: "rgb_weed_water", crop_type: "", variety: "", season: "", growth_stage: "",
  row_direction_deg: null, expected_row_spacing_m: null, target_gsd_cm: 2, speed_mps: 5, front_overlap_pct: 70, side_overlap_pct: 60,
  camera_orientation: "nadir", fov_h_deg: 78, fov_v_deg: 62, camera_resolution_width_px: 4000, camera_resolution_height_px: 3000,
  focal_length_mm: null, grid_angle_deg: 0, sensor_inventory: ["rgb"], calibration_ids: [], requested_analyses: ["quality", "coverage"], repeat_interval_days: null,
};

export function AgricultureFlightPlanner({
  fieldId,
  fieldPolygon,
  fieldProfile,
}: { fieldId: number; fieldPolygon?: number[][] | null; fieldProfile?: AgricultureFieldProfile | null }) {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<AgricultureMissionProfile>({ ...defaultProfile, ...fieldProfile, crop_type: fieldProfile?.crop_type ?? "", variety: fieldProfile?.variety ?? "", season: fieldProfile?.season ?? "", growth_stage: fieldProfile?.growth_stage ?? "" });
  const [values, setValues] = useState<AgriculturePlannerValues>({ altitude: 30, rowSpacing: 7.5, gridAngle: 0, safetyInset: 1.5, pattern: "boustrophedon", exclusionZones: [], checks: {}, takeoff: "", landing: "", maxWaypointsPerSegment: 500 });
  const [plan, setPlan] = useState<import("../types").AgriculturePlan | null>(null);
  const [preflight, setPreflight] = useState<import("../types").AgriculturePreflightSnapshot | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const fieldContext = useAgricultureFieldContext(fieldId);
  const [zonesLoaded, setZonesLoaded] = useState(false);
  const createPlan = useCreateAgriculturePlan();
  const evaluate = useEvaluateAgriculturePreflight();
  const acknowledge = useAcknowledgeAgriculturePreflight();
  const updateGrid = useUpdateAgriculturePlanGrid();
  const disabled = createPlan.isPending || evaluate.isPending || acknowledge.isPending;
  useEffect(() => {
    if (!fieldContext.data || zonesLoaded) return;
    const exclusions = fieldContext.data.zones.filter((zone) => zone.zone_type === "exclusion").map((zone) => ({ geometry: zone.geometry, id: zone.id, kind: zone.kind }));
    const obstacles = fieldContext.data.zones.filter((zone) => zone.zone_type === "obstacle").map((zone) => ({ geometry: zone.geometry, id: zone.id, kind: zone.kind, radius_m: zone.radius_m }));
    // Server-owned safety zones hydrate the planner once per field context.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setValues((current) => ({ ...current, exclusionZones: [...exclusions, ...obstacles] }));
    setZonesLoaded(true);
  }, [fieldContext.data, zonesLoaded]);
  const onBuildPlan = async () => {
    setActionError(null);
    if (!fieldPolygon || fieldPolygon.length < 3) return;
    try {
      const next = await createPlan.mutateAsync({ field_id: fieldId, field_polygon_lonlat: fieldPolygon, cruise_alt_m: values.altitude, row_spacing_m: values.rowSpacing, grid_angle_deg: values.gridAngle, safety_inset_m: values.safetyInset, max_waypoints_per_segment: values.maxWaypointsPerSegment, pattern_mode: values.pattern, crosshatch_angle_offset_deg: 90, lane_strategy: "serpentine", start_corner: "auto", row_stride: 1, row_phase_m: 0, exclusion_zones: values.exclusionZones, takeoff_point_lonlat: parsePoint(values.takeoff), landing_point_lonlat: parsePoint(values.landing), profile: { ...profile, grid_angle_deg: values.gridAngle } });
      setPlan(next); setPreflight(null);
    } catch (error) { setActionError(error instanceof Error ? error.message : "Could not save agriculture plan."); }
  };
  const onEvaluate = async () => {
    setActionError(null);
    if (plan) {
      try {
        setPreflight(await evaluate.mutateAsync({
          planId: plan.id,
          notes: "Agriculture operator requested authoritative server pre-flight evaluation.",
        }));
      } catch (error) { setActionError(error instanceof Error ? error.message : "Could not evaluate pre-flight."); }
    }
  };
  const onAcknowledge = async () => {
    setActionError(null);
    if (preflight) {
      try { setPreflight(await acknowledge.mutateAsync(preflight.id)); }
      catch (error) { setActionError(error instanceof Error ? error.message : "Could not acknowledge pre-flight."); }
    }
  };
  const onStart = async () => {
    if (!plan || !preflight || !fieldPolygon) return;
    try {
      const savedRoute = (plan.route_geojson.coordinates as number[][]).map(([lon, lat]) => ({ lon, lat, alt: values.altitude }));
      const result = await startAgricultureFlight({ name: `agriculture-field-${fieldId}`, cruise_alt: values.altitude, mission_type: "grid", field_id: fieldId, agriculture: { ...profile, plan_id: plan.id, preflight_snapshot_id: preflight.id }, grid: { field_polygon_lonlat: fieldPolygon, route_waypoints: savedRoute, row_spacing_m: values.rowSpacing, grid_angle_deg: values.gridAngle, safety_inset_m: 1.5, agl_m: values.altitude, pattern_mode: values.pattern, crosshatch_angle_offset_deg: 90, lane_strategy: "serpentine", start_corner: "auto", row_stride: 1, row_phase_m: 0, slope_aware: false, terrain_follow: false } });
      navigate(`/dashboard/agriculture/flights/${result.flight_id}`);
    } catch (error) { setActionError(error instanceof Error ? error.message : "Agriculture flight could not start."); }
  };
  if (!fieldPolygon || fieldPolygon.length < 3) return <Alert severity="info">Open the field planner to draw or select a valid field boundary before creating an agriculture plan.</Alert>;
  return (
    <Stack spacing={1.5} component="section" aria-labelledby="agriculture-flight-planner-heading">
      <Typography id="agriculture-flight-planner-heading" variant="h6">Agriculture survey planner</Typography>
      <AgriculturePlannerForm profile={profile} values={values} onProfileChange={(patch) => setProfile((current) => ({ ...current, ...patch }))} onChange={(patch) => setValues((current) => ({ ...current, ...patch }))} disabled={disabled} onBuildPlan={() => void onBuildPlan()} onEvaluate={() => void onEvaluate()} onAcknowledge={() => void onAcknowledge()} onStart={() => void onStart()} planStatus={plan?.status ?? null} preflightStatus={preflight?.status ?? null} acknowledged={Boolean(preflight?.acknowledged)} preflight={preflight} />
      {plan ? <AgricultureGridEditor plan={plan} disabled={updateGrid.isPending || disabled} onSave={(route) => { updateGrid.mutate({ planId: plan.id, expectedRevision: plan.grid_revision, routeLonlat: route }, { onSuccess: setPlan, onError: (error) => setActionError(error instanceof Error ? error.message : "Could not save grid revision.") }); }} /> : null}
      {actionError || createPlan.error || evaluate.error || acknowledge.error ? <Alert severity="error">{actionError ?? (createPlan.error ?? evaluate.error ?? acknowledge.error)?.message ?? "Agriculture workflow action failed."}</Alert> : null}
      {createPlan.isPending ? <CircularProgress size={20} aria-label="Saving agriculture plan" /> : null}
    </Stack>
  );
}

function parsePoint(value: string): number[] | null {
  if (!value.trim()) return null;
  const parts = value.split(",").map(Number);
  return parts.length === 2 && parts.every(Number.isFinite) ? parts : null;
}
