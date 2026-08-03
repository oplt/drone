import { Alert, Chip, Stack, Typography } from "@mui/material";
import type { AgricultureSensorStatus } from "../types";

export function SensorCalibrationPanel({
  status,
}: {
  status: AgricultureSensorStatus | undefined;
}) {
  if (!status)
    return (
      <Alert severity="info">
        Sensor inventory and calibration status are loading.
      </Alert>
    );
  const spectralStatus = String(status.spectral.status ?? "unknown");
  return (
    <Stack
      component="section"
      aria-labelledby="sensor-calibration-heading"
      spacing={0.75}
    >
      <Typography id="sensor-calibration-heading" variant="subtitle2">
        Sensor calibration
      </Typography>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
        <Chip
          size="small"
          label={`Inventory: ${status.inventory.join(", ") || "none"}`}
        />
        <Chip
          size="small"
          color={status.status === "pass" ? "success" : "warning"}
          label={`Readiness: ${status.status}`}
        />
        <Chip
          size="small"
          variant="outlined"
          label={`Calibration refs: ${status.calibration_ids.length}`}
        />
        <Chip
          size="small"
          variant="outlined"
          label={`Spectral: ${spectralStatus}`}
        />
        <Chip size="small" label={`Calibration: ${status.calibration_status ?? "unknown"}`} color={status.calibration_status === "pass" || status.calibration_status === "not_required" ? "success" : "warning"} />
      </Stack>
      {status.calibrations?.map((calibration) => <Typography key={calibration.id} variant="caption" color={calibration.valid ? "text.secondary" : "error.main"}>{calibration.sensor_type} {calibration.version} · {calibration.valid ? "current" : "expired or not yet valid"} · checksum {calibration.checksum.slice(0, 12)}…</Typography>)}
      {spectralStatus !== "pass" && spectralStatus !== "not_required" ? (
        <Alert severity="warning">
          Spectral and thermal outputs remain not measured until alignment and
          calibration pass.
        </Alert>
      ) : null}
    </Stack>
  );
}
