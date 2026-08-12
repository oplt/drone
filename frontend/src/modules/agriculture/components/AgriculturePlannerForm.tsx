import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Chip,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { AgricultureMissionProfile } from "../types";
import type { AgriculturePreflightSnapshot } from "../types";
import { AgricultureServerPreflightPanel } from "./AgricultureServerPreflightPanel";
import { AgricultureGeometryMapEditor } from "./AgricultureGeometryMapEditor";
import type { AgricultureLonLat } from "../geometry";

export type AgriculturePlannerValues = {
  altitude: number;
  rowSpacing: number;
  gridAngle: number;
  safetyInset: number;
  pattern: "boustrophedon" | "crosshatch";
  exclusionZones: Array<Record<string, unknown>>;
  checks: Record<string, boolean | null>;
  takeoff: string;
  landing: string;
  maxWaypointsPerSegment: number;
};

export function AgriculturePlannerForm({
  profile,
  values,
  onProfileChange,
  onChange,
  disabled,
  onBuildPlan,
  onEvaluate,
  onAcknowledge,
  onStart,
  planStatus,
  preflightStatus,
  acknowledged,
  preflight,
  fieldBoundary,
}: {
  profile: AgricultureMissionProfile;
  values: AgriculturePlannerValues;
  onProfileChange: (patch: Partial<AgricultureMissionProfile>) => void;
  onChange: (patch: Partial<AgriculturePlannerValues>) => void;
  disabled: boolean;
  onBuildPlan: () => void;
  onEvaluate: () => void;
  onAcknowledge: () => void;
  onStart: () => void;
  planStatus: string | null;
  preflightStatus: string | null;
  acknowledged: boolean;
  preflight: AgriculturePreflightSnapshot | null;
  fieldBoundary?: AgricultureLonLat[] | null;
}) {
  const templates: Array<{ label: string; patch: Partial<AgricultureMissionProfile> & { altitude: number; rowSpacing: number } }> = [
    { label: "Capture quality", patch: { preset: "repeat_monitoring", requested_analyses: ["quality", "coverage"], target_gsd_cm: 3, front_overlap_pct: 75, side_overlap_pct: 65, altitude: 40, rowSpacing: 8 } },
    { label: "Stand count", patch: { preset: "early_stand_count", requested_analyses: ["quality", "stand_count"], target_gsd_cm: 1.2, front_overlap_pct: 80, side_overlap_pct: 75, altitude: 22, rowSpacing: 5 } },
    { label: "Canopy / health", patch: { preset: "repeat_monitoring", requested_analyses: ["quality", "canopy_cover", "crop_health"], target_gsd_cm: 2, front_overlap_pct: 78, side_overlap_pct: 70, altitude: 30, rowSpacing: 6 } },
    { label: "Scouting", patch: { preset: "rgb_weed_water", requested_analyses: ["quality", "weed_detection", "standing_water"], target_gsd_cm: 1.5, front_overlap_pct: 80, side_overlap_pct: 75, altitude: 25, rowSpacing: 5 } },
  ];
  return (
    <Stack spacing={1.5} component="section" aria-labelledby="agri-planner-form-title">
      <Typography id="agri-planner-form-title" variant="subtitle1">Survey parameters</Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap aria-label="Survey goal templates">
        {templates.map(({ label, patch }) => (
          <Chip
            key={label}
            clickable
            label={label}
            onClick={() => {
              const { altitude, rowSpacing, ...profilePatch } = patch;
              onProfileChange(profilePatch);
              onChange({ altitude, rowSpacing });
            }}
            sx={{ minHeight: 44 }}
          />
        ))}
      </Stack>
      <AgricultureGeometryMapEditor
        boundary={fieldBoundary ?? null}
        exclusionZones={values.exclusionZones.flatMap((zone) => {
          const geometry = zone.geometry as { type?: string; coordinates?: unknown } | undefined;
          return geometry?.type === "Polygon" && Array.isArray(geometry.coordinates)
            ? [geometry.coordinates[0] as AgricultureLonLat[]]
            : [];
        })}
        onExclusionZone={(ring) => onChange({ exclusionZones: [...values.exclusionZones, { geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] } }] })}
        onPointPick={(kind, point) => onChange({ [kind]: `${point[0]}, ${point[1]}` })}
      />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField label="Altitude (m)" type="number" value={values.altitude} onChange={(e) => onChange({ altitude: Number(e.target.value) })} inputProps={{ min: 1, max: 500 }} />
        <TextField label="Row spacing (m)" type="number" value={values.rowSpacing} onChange={(e) => onChange({ rowSpacing: Number(e.target.value) })} inputProps={{ min: 1, max: 200 }} />
        <TextField label="Grid angle (°)" type="number" value={values.gridAngle} onChange={(e) => onChange({ gridAngle: Number(e.target.value) })} inputProps={{ min: 0, max: 179 }} />
        <TextField label="Inset (m)" type="number" value={values.safetyInset} onChange={(e) => onChange({ safetyInset: Number(e.target.value) })} inputProps={{ min: 0, max: 100 }} />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField select label="Pattern" value={values.pattern} onChange={(e) => onChange({ pattern: e.target.value as AgriculturePlannerValues["pattern"] })} sx={{ minWidth: 180 }}>
          <MenuItem value="boustrophedon">Serpentine</MenuItem>
          <MenuItem value="crosshatch">Crosshatch</MenuItem>
        </TextField>
        <TextField label="Crop" value={profile.crop_type ?? ""} onChange={(e) => onProfileChange({ crop_type: e.target.value })} />
        <TextField label="Growth stage" value={profile.growth_stage ?? ""} onChange={(e) => onProfileChange({ growth_stage: e.target.value })} />
      </Stack>
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Advanced coordinates and route limits</AccordionSummary>
        <AccordionDetails>
          <Stack spacing={1}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField label="Take-off [lon, lat]" value={values.takeoff} onChange={(e) => onChange({ takeoff: e.target.value })} placeholder="4.351, 50.850" />
              <TextField label="Landing [lon, lat]" value={values.landing} onChange={(e) => onChange({ landing: e.target.value })} placeholder="4.351, 50.850" />
              <TextField label="Max waypoints / segment" type="number" value={values.maxWaypointsPerSegment} onChange={(e) => onChange({ maxWaypointsPerSegment: Number(e.target.value) })} inputProps={{ min: 2, max: 10000 }} />
            </Stack>
            <TextField
              label="Exclusion zones GeoJSON"
              value={JSON.stringify(values.exclusionZones)}
              onChange={(e) => {
                try { onChange({ exclusionZones: JSON.parse(e.target.value) as Array<Record<string, unknown>> }); } catch { /* retain last valid geometry */ }
              }}
              helperText="Advanced exact geometry. Draw zones on the map for the normal workflow."
              multiline
              minRows={2}
            />
          </Stack>
        </AccordionDetails>
      </Accordion>
      <AgricultureServerPreflightPanel snapshot={preflight} />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <Button variant="outlined" onClick={onBuildPlan} disabled={disabled}>Generate and save plan</Button>
        <Button variant="outlined" onClick={onEvaluate} disabled={disabled || planStatus !== "validated"}>Refresh server pre-flight</Button>
        <Button variant="outlined" onClick={onAcknowledge} disabled={disabled || preflightStatus !== "pass" || acknowledged}>Acknowledge checklist</Button>
        <Button variant="contained" onClick={onStart} disabled={disabled || planStatus !== "validated" || !acknowledged}>Start agriculture flight</Button>
      </Stack>
      {planStatus === "invalid" ? <Alert severity="error">Plan is invalid. Adjust the parameters or exclusion zones.</Alert> : null}
      {preflightStatus === "blocked" ? <Alert severity="warning">All blocking pre-flight checks must pass before launch.</Alert> : null}
      {acknowledged ? <Alert severity="success">Agriculture pre-flight acknowledged. Snapshot expires shortly.</Alert> : null}
    </Stack>
  );
}
