import {
  Alert,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import type { AgricultureMissionProfile } from "../types";
import type { AgriculturePreflightSnapshot } from "../types";
import { AgricultureServerPreflightPanel } from "./AgricultureServerPreflightPanel";

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
}) {
  return (
    <Stack spacing={1.5} component="section" aria-labelledby="agri-planner-form-title">
      <Typography id="agri-planner-form-title" variant="subtitle1">Survey parameters</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField label="Altitude (m)" type="number" value={values.altitude} onChange={(e) => onChange({ altitude: Number(e.target.value) })} inputProps={{ min: 1, max: 500 }} />
        <TextField label="Row spacing (m)" type="number" value={values.rowSpacing} onChange={(e) => onChange({ rowSpacing: Number(e.target.value) })} inputProps={{ min: 1, max: 200 }} />
        <TextField label="Grid angle (°)" type="number" value={values.gridAngle} onChange={(e) => onChange({ gridAngle: Number(e.target.value) })} inputProps={{ min: 0, max: 179 }} />
        <TextField label="Inset (m)" type="number" value={values.safetyInset} onChange={(e) => onChange({ safetyInset: Number(e.target.value) })} inputProps={{ min: 0, max: 100 }} />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField label="Take-off [lon, lat]" value={values.takeoff} onChange={(e) => onChange({ takeoff: e.target.value })} placeholder="4.351, 50.850" />
        <TextField label="Landing [lon, lat]" value={values.landing} onChange={(e) => onChange({ landing: e.target.value })} placeholder="4.351, 50.850" />
        <TextField label="Max waypoints / segment" type="number" value={values.maxWaypointsPerSegment} onChange={(e) => onChange({ maxWaypointsPerSegment: Number(e.target.value) })} inputProps={{ min: 2, max: 10000 }} />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField select label="Pattern" value={values.pattern} onChange={(e) => onChange({ pattern: e.target.value as AgriculturePlannerValues["pattern"] })} sx={{ minWidth: 180 }}>
          <MenuItem value="boustrophedon">Serpentine</MenuItem>
          <MenuItem value="crosshatch">Crosshatch</MenuItem>
        </TextField>
        <TextField label="Crop" value={profile.crop_type ?? ""} onChange={(e) => onProfileChange({ crop_type: e.target.value })} />
        <TextField label="Growth stage" value={profile.growth_stage ?? ""} onChange={(e) => onProfileChange({ growth_stage: e.target.value })} />
      </Stack>
      <TextField
        label="Exclusion zones (GeoJSON JSON, optional)"
        value={JSON.stringify(values.exclusionZones)}
        onChange={(e) => {
          try { onChange({ exclusionZones: JSON.parse(e.target.value) as Array<Record<string, unknown>> }); } catch { /* retain last valid geometry */ }
        }}
        helperText="Polygon features are excluded from the generated route; invalid JSON is ignored until corrected."
        multiline
        minRows={2}
      />
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
