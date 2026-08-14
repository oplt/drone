import {
  Alert,
  Box,
  Button,
  FormControlLabel,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import type {
  AgricultureMapContextStatus,
  AgricultureMapLayerKey,
  AgricultureMapLayerVisibility,
} from "./types";

const layerLabels: Array<[AgricultureMapLayerKey, string]> = [
  ["fieldBoundary", "Field boundary"],
  ["flightPath", "Flown path"],
  ["observations", "Observation clusters"],
  ["severity", "Severity areas"],
  ["heatmap", "Density heatmap"],
  ["temporalChanges", "Temporal changes"],
  ["interventionZones", "Intervention zones"],
];

export function AgricultureMapControls({
  visibility,
  available,
  contextStatus,
  onToggle,
  onFit,
}: {
  visibility: AgricultureMapLayerVisibility;
  available: AgricultureMapLayerVisibility;
  contextStatus?: AgricultureMapContextStatus;
  onToggle: (key: AgricultureMapLayerKey) => void;
  onFit: () => void;
}) {
  return (
    <Stack spacing={1}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        useFlexGap
      >
        <Typography variant="subtitle2">Analysis map layers</Typography>
        <Button size="small" variant="outlined" onClick={onFit}>
          Fit map to data
        </Button>
      </Stack>
      <Stack
        component="fieldset"
        aria-label="Map layer visibility"
        direction="row"
        flexWrap="wrap"
        useFlexGap
        sx={{ m: 0, p: 0, border: 0, columnGap: 1.5 }}
      >
        {layerLabels.map(([key, label]) => (
          <FormControlLabel
            key={key}
            control={
              <Switch
                size="small"
                checked={visibility[key]}
                disabled={!available[key]}
                onChange={() => onToggle(key)}
                inputProps={{ "aria-label": label }}
              />
            }
            label={label}
            sx={{ minHeight: 44, mr: 0 }}
          />
        ))}
      </Stack>
      <Stack
        component="aside"
        aria-label="Map legend"
        direction="row"
        spacing={2}
        flexWrap="wrap"
        useFlexGap
      >
        {[
          ["#2e7d32", "Low"],
          ["#ed6c02", "Medium"],
          ["#c62828", "High"],
        ].map(([color, label]) => (
          <Typography key={label} variant="caption">
            <Box
              component="span"
              aria-hidden="true"
              sx={{
                display: "inline-block",
                width: 10,
                height: 10,
                bgcolor: color,
                border: "1px solid",
                borderColor: "text.primary",
                mr: 0.5,
              }}
            />
            {label} severity / density
          </Typography>
        ))}
        <Typography variant="caption">Blue line: recorded flight path</Typography>
        <Typography variant="caption">Change: red new · blue persistent · green resolved</Typography>
        <Typography variant="caption">Zone: purple proposed · green approved · gray rejected</Typography>
      </Stack>
      {contextStatus?.fieldBoundary === "unavailable" ? (
        <Alert severity="info">
          Field boundary is unavailable; findings retain their recorded
          coordinates.
        </Alert>
      ) : null}
      {contextStatus?.flightPath === "unavailable" ? (
        <Alert severity="info">
          Recorded telemetry is unavailable, so no flown path is shown.
        </Alert>
      ) : null}
      {contextStatus?.flightPath === "partial" ? (
        <Alert severity="warning">
          The flown path is partial because the telemetry response was capped.
        </Alert>
      ) : null}
    </Stack>
  );
}
