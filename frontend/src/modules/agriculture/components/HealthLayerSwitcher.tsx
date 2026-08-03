import { MenuItem, Select, Slider, Stack, Typography } from "@mui/material";

const HEALTH_LAYERS = [
  "all",
  "quality",
  "canopy",
  "soil",
  "rows",
  "weed",
  "standing_water",
  "stand_count",
  "emergence_issue",
  "abnormal_crop_health_signature",
  "agriculture_anomaly",
  "rgb_metrics",
  "ndvi",
  "gndvi",
  "thermal",
  "fusion_risk",
];

export function HealthLayerSwitcher({
  layer,
  onLayerChange,
  confidence,
  onConfidenceChange,
  severity,
  onSeverityChange,
}: {
  layer: string;
  onLayerChange: (value: string) => void;
  confidence: number;
  onConfidenceChange: (value: number) => void;
  severity: number;
  onSeverityChange: (value: number) => void;
}) {
  return (
    <Stack
      component="section"
      aria-label="Health layer controls"
      direction={{ xs: "column", sm: "row" }}
      spacing={1}
      alignItems={{ sm: "center" }}
    >
      <Select
        size="small"
        value={layer}
        onChange={(event) => onLayerChange(event.target.value)}
        sx={{ minWidth: 210 }}
        inputProps={{ "aria-label": "Health layer" }}
      >
        {HEALTH_LAYERS.map((value) => (
          <MenuItem key={value} value={value}>
            {value.replaceAll("_", " ")}
          </MenuItem>
        ))}
      </Select>
      <Typography variant="caption">
        Confidence {Math.round(confidence * 100)}%
      </Typography>
      <Slider
        value={confidence}
        min={0}
        max={1}
        step={0.05}
        onChange={(_, value) => onConfidenceChange(value as number)}
        sx={{ width: 120 }}
        aria-label="Confidence threshold"
      />
      <Typography variant="caption">
        Severity {Math.round(severity * 100)}%
      </Typography>
      <Slider
        value={severity}
        min={0}
        max={1}
        step={0.05}
        onChange={(_, value) => onSeverityChange(value as number)}
        sx={{ width: 120 }}
        aria-label="Severity threshold"
      />
    </Stack>
  );
}
