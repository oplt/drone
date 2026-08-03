import {
  Alert,
  Button,
  Chip,
  Divider,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useAgricultureFusionResults,
  useAgricultureSensorStatus,
  useProcessAgricultureFusion,
} from "../hooks";
import { SensorCalibrationPanel } from "./SensorCalibrationPanel";

function percent(value: unknown): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

export function AgricultureSensorFusionPanel({
  flightId,
  runId,
  active = false,
}: {
  flightId: string;
  runId: string;
  active?: boolean;
}) {
  const sensor = useAgricultureSensorStatus(flightId, active);
  const results = useAgricultureFusionResults(runId);
  const process = useProcessAgricultureFusion();
  const [selected, setSelected] = useState("");
  const rows = results.data ?? [];
  const current = rows.find(
    (row) => row.layer === (selected || rows[0]?.layer),
  );
  const readiness = sensor.data;
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.25}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          spacing={1}
        >
          <div>
            <Typography variant="subtitle2">Sensor fusion</Typography>
            <Typography variant="caption" color="text.secondary">
              Measured outputs require registered bands, alignment, calibration,
              and fresh sensors.
            </Typography>
          </div>
          <Button
            size="small"
            variant="outlined"
            onClick={() => process.mutate({ runId })}
            disabled={process.isPending}
          >
            {process.isPending ? "Evaluating…" : "Evaluate fusion"}
          </Button>
        </Stack>
        {sensor.isError ? (
          <Alert severity="warning">
            Sensor readiness unavailable; no sensor output is assumed.
          </Alert>
        ) : null}
        <SensorCalibrationPanel status={readiness} />
        {process.error ? (
          <Alert severity="error">
            Fusion evaluation failed. Retry after checking sensor readiness.
          </Alert>
        ) : null}
        <Divider />
        {results.isLoading ? (
          <Typography variant="caption">Loading sensor layers…</Typography>
        ) : rows.length === 0 ? (
          <Alert severity="info">
            No fusion result yet. RGB-only flights expose RGB-derived metrics
            only; NDVI and thermal remain not measured.
          </Alert>
        ) : (
          <>
            <Select
              size="small"
              value={current?.layer ?? ""}
              onChange={(event) => setSelected(event.target.value)}
              displayEmpty
              inputProps={{ "aria-label": "Sensor layer" }}
            >
              {rows.map((row) => (
                <MenuItem key={row.layer} value={row.layer}>
                  {row.layer.replaceAll("_", " ")}
                </MenuItem>
              ))}
            </Select>
            {current ? (
              <Stack spacing={0.75}>
                <Stack
                  direction="row"
                  spacing={0.75}
                  flexWrap="wrap"
                  useFlexGap
                >
                  <Chip
                    size="small"
                    label={current.measured ? "Measured" : "Not measured"}
                    color={current.measured ? "success" : "warning"}
                  />
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`Units: ${current.units ?? "—"}`}
                  />
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`Confidence: ${percent(current.confidence)}`}
                  />
                </Stack>
                <Typography variant="body2">
                  {current.measured
                    ? JSON.stringify(current.summary)
                    : `Not measured: ${current.failure_reasons.join(", ") || "required calibrated input unavailable"}.`}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Sources: {current.source_ids.join(", ") || "none"} ·
                  timestamps: {current.source_timestamps.join(", ") || "none"} ·
                  model: {current.model_version ?? "none"}
                </Typography>
                {current.layer === "fusion_risk" ? (
                  <Alert severity="info">
                    Risk is a suspected issue signature for inspection, not a
                    confirmed disease diagnosis.
                  </Alert>
                ) : null}
              </Stack>
            ) : null}
          </>
        )}
      </Stack>
    </Paper>
  );
}
