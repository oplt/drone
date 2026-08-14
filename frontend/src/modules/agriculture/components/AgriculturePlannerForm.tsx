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
import { Formik, Form } from "formik";
import type { AgricultureMissionProfile } from "../types";
import type { AgriculturePreflightSnapshot } from "../types";
import { AgricultureServerPreflightPanel } from "./AgricultureServerPreflightPanel";
import { AgricultureGeometryMapEditor } from "./AgricultureGeometryMapEditor";
import type { AgricultureLonLat } from "../geometry";
import {
  agriculturePlannerSchema,
  type AgriculturePlannerFormValues,
} from "../../../shared/forms/opsValidation";

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

function toFormValues(
  values: AgriculturePlannerValues,
  profile: AgricultureMissionProfile,
): AgriculturePlannerFormValues {
  return {
    altitude: values.altitude,
    rowSpacing: values.rowSpacing,
    gridAngle: values.gridAngle,
    safetyInset: values.safetyInset,
    front_overlap_pct: profile.front_overlap_pct,
    side_overlap_pct: profile.side_overlap_pct,
  };
}

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
  const templates: Array<{
    label: string;
    patch: Partial<AgricultureMissionProfile> & { altitude: number; rowSpacing: number };
  }> = [
    {
      label: "Capture quality",
      patch: {
        preset: "repeat_monitoring",
        requested_analyses: ["quality", "coverage"],
        target_gsd_cm: 3,
        front_overlap_pct: 75,
        side_overlap_pct: 65,
        altitude: 40,
        rowSpacing: 8,
      },
    },
    {
      label: "Stand count",
      patch: {
        preset: "early_stand_count",
        requested_analyses: ["quality", "stand_count"],
        target_gsd_cm: 1.2,
        front_overlap_pct: 80,
        side_overlap_pct: 75,
        altitude: 22,
        rowSpacing: 5,
      },
    },
    {
      label: "Canopy / health",
      patch: {
        preset: "repeat_monitoring",
        requested_analyses: ["quality", "canopy_cover", "crop_health"],
        target_gsd_cm: 2,
        front_overlap_pct: 78,
        side_overlap_pct: 70,
        altitude: 30,
        rowSpacing: 6,
      },
    },
    {
      label: "Scouting",
      patch: {
        preset: "rgb_weed_water",
        requested_analyses: ["quality", "weed_detection", "standing_water"],
        target_gsd_cm: 1.5,
        front_overlap_pct: 80,
        side_overlap_pct: 75,
        altitude: 25,
        rowSpacing: 5,
      },
    },
  ];

  return (
    <Formik
      enableReinitialize
      initialValues={toFormValues(values, profile)}
      validationSchema={agriculturePlannerSchema}
      validateOnMount
      onSubmit={() => {
        onBuildPlan();
      }}
    >
      {({
        values: formValues,
        errors,
        touched,
        handleBlur,
        setFieldValue,
        isValid,
        submitCount,
      }) => {
        const showError = (field: keyof AgriculturePlannerFormValues) =>
          Boolean((touched[field] || submitCount > 0) && errors[field]);
        const fieldError = (field: keyof AgriculturePlannerFormValues) =>
          showError(field) ? String(errors[field]) : undefined;

        const syncNumber = (
          field: keyof AgriculturePlannerFormValues,
          raw: string,
          apply: (n: number) => void,
        ) => {
          const n = Number(raw);
          void setFieldValue(field, Number.isFinite(n) ? n : raw, true);
          if (Number.isFinite(n)) apply(n);
        };

        return (
          <Stack
            spacing={1.5}
            component={Form}
            aria-labelledby="agri-planner-form-title"
            noValidate
          >
            <Typography id="agri-planner-form-title" variant="subtitle1">
              Survey parameters
            </Typography>
            <Stack
              direction="row"
              spacing={1}
              flexWrap="wrap"
              useFlexGap
              aria-label="Survey goal templates"
            >
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
                const geometry = zone.geometry as
                  | { type?: string; coordinates?: unknown }
                  | undefined;
                return geometry?.type === "Polygon" && Array.isArray(geometry.coordinates)
                  ? [geometry.coordinates[0] as AgricultureLonLat[]]
                  : [];
              })}
              onExclusionZone={(ring) =>
                onChange({
                  exclusionZones: [
                    ...values.exclusionZones,
                    { geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] } },
                  ],
                })
              }
              onPointPick={(kind, point) => onChange({ [kind]: `${point[0]}, ${point[1]}` })}
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                label="Altitude (m)"
                type="number"
                name="altitude"
                value={formValues.altitude}
                onBlur={handleBlur}
                onChange={(e) =>
                  syncNumber("altitude", e.target.value, (n) => onChange({ altitude: n }))
                }
                error={showError("altitude")}
                helperText={fieldError("altitude")}
                inputProps={{ min: 5, max: 120 }}
              />
              <TextField
                label="Row spacing (m)"
                type="number"
                name="rowSpacing"
                value={formValues.rowSpacing}
                onBlur={handleBlur}
                onChange={(e) =>
                  syncNumber("rowSpacing", e.target.value, (n) => onChange({ rowSpacing: n }))
                }
                error={showError("rowSpacing")}
                helperText={fieldError("rowSpacing")}
                inputProps={{ min: 1, max: 200 }}
              />
              <TextField
                label="Grid angle (°)"
                type="number"
                name="gridAngle"
                value={formValues.gridAngle}
                onBlur={handleBlur}
                onChange={(e) =>
                  syncNumber("gridAngle", e.target.value, (n) => onChange({ gridAngle: n }))
                }
                error={showError("gridAngle")}
                helperText={fieldError("gridAngle")}
                inputProps={{ min: 0, max: 179 }}
              />
              <TextField
                label="Inset (m)"
                type="number"
                name="safetyInset"
                value={formValues.safetyInset}
                onBlur={handleBlur}
                onChange={(e) =>
                  syncNumber("safetyInset", e.target.value, (n) => onChange({ safetyInset: n }))
                }
                error={showError("safetyInset")}
                helperText={fieldError("safetyInset")}
                inputProps={{ min: 0, max: 100 }}
              />
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                label="Front overlap (%)"
                type="number"
                name="front_overlap_pct"
                value={formValues.front_overlap_pct}
                onBlur={handleBlur}
                onChange={(e) =>
                  syncNumber("front_overlap_pct", e.target.value, (n) =>
                    onProfileChange({ front_overlap_pct: n }),
                  )
                }
                error={showError("front_overlap_pct")}
                helperText={fieldError("front_overlap_pct")}
                inputProps={{ min: 50, max: 95 }}
              />
              <TextField
                label="Side overlap (%)"
                type="number"
                name="side_overlap_pct"
                value={formValues.side_overlap_pct}
                onBlur={handleBlur}
                onChange={(e) =>
                  syncNumber("side_overlap_pct", e.target.value, (n) =>
                    onProfileChange({ side_overlap_pct: n }),
                  )
                }
                error={showError("side_overlap_pct")}
                helperText={fieldError("side_overlap_pct")}
                inputProps={{ min: 40, max: 95 }}
              />
              <TextField
                select
                label="Pattern"
                value={values.pattern}
                onChange={(e) =>
                  onChange({ pattern: e.target.value as AgriculturePlannerValues["pattern"] })
                }
                sx={{ minWidth: 180 }}
              >
                <MenuItem value="boustrophedon">Serpentine</MenuItem>
                <MenuItem value="crosshatch">Crosshatch</MenuItem>
              </TextField>
              <TextField
                label="Crop"
                value={profile.crop_type ?? ""}
                onChange={(e) => onProfileChange({ crop_type: e.target.value })}
              />
              <TextField
                label="Growth stage"
                value={profile.growth_stage ?? ""}
                onChange={(e) => onProfileChange({ growth_stage: e.target.value })}
              />
            </Stack>
            {!isValid ? (
              <Alert severity="warning">
                Fix altitude and overlap errors before generating a plan.
              </Alert>
            ) : null}
            <Accordion>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                Advanced coordinates and route limits
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1}>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <TextField
                      label="Take-off [lon, lat]"
                      value={values.takeoff}
                      onChange={(e) => onChange({ takeoff: e.target.value })}
                      placeholder="4.351, 50.850"
                    />
                    <TextField
                      label="Landing [lon, lat]"
                      value={values.landing}
                      onChange={(e) => onChange({ landing: e.target.value })}
                      placeholder="4.351, 50.850"
                    />
                    <TextField
                      label="Max waypoints / segment"
                      type="number"
                      value={values.maxWaypointsPerSegment}
                      onChange={(e) =>
                        onChange({ maxWaypointsPerSegment: Number(e.target.value) })
                      }
                      inputProps={{ min: 2, max: 10000 }}
                    />
                  </Stack>
                  <TextField
                    label="Exclusion zones GeoJSON"
                    value={JSON.stringify(values.exclusionZones)}
                    onChange={(e) => {
                      try {
                        onChange({
                          exclusionZones: JSON.parse(e.target.value) as Array<
                            Record<string, unknown>
                          >,
                        });
                      } catch {
                        /* retain last valid geometry */
                      }
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
              <Button type="submit" variant="outlined" disabled={disabled || !isValid}>
                Generate and save plan
              </Button>
              <Button
                type="button"
                variant="outlined"
                onClick={onEvaluate}
                disabled={disabled || planStatus !== "validated"}
              >
                Refresh server pre-flight
              </Button>
              <Button
                type="button"
                variant="outlined"
                onClick={onAcknowledge}
                disabled={disabled || preflightStatus !== "pass" || acknowledged}
              >
                Acknowledge checklist
              </Button>
              <Button
                type="button"
                variant="contained"
                onClick={onStart}
                disabled={disabled || planStatus !== "validated" || !acknowledged}
              >
                Start agriculture flight
              </Button>
            </Stack>
            {planStatus === "invalid" ? (
              <Alert severity="error">
                Plan is invalid. Adjust the parameters or exclusion zones.
              </Alert>
            ) : null}
            {preflightStatus === "blocked" ? (
              <Alert severity="warning">
                All blocking pre-flight checks must pass before launch.
              </Alert>
            ) : null}
            {acknowledged ? (
              <Alert severity="success">
                Agriculture pre-flight acknowledged. Snapshot expires shortly.
              </Alert>
            ) : null}
          </Stack>
        );
      }}
    </Formik>
  );
}
