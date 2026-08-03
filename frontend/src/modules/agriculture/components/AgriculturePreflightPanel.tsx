import { Alert, Chip, Divider, Stack, Typography } from "@mui/material";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import type { AgricultureMissionProfile } from "../types";

function nested(value: Record<string, unknown>, paths: string[]): unknown {
  for (const path of paths) {
    let current: unknown = value;
    for (const key of path.split("."))
      current =
        current && typeof current === "object"
          ? (current as Record<string, unknown>)[key]
          : undefined;
    if (current != null) return current;
  }
  return null;
}
function boolValue(value: unknown): boolean | null {
  return typeof value === "boolean"
    ? value
    : typeof value === "number"
      ? value > 0
      : typeof value === "string"
        ? ["true", "ready", "ok", "connected"].includes(value.toLowerCase())
        : null;
}

export function AgriculturePreflightPanel({
  fieldId,
  profile,
  telemetry,
  droneConnected,
  wsConnected,
}: {
  fieldId: number | null;
  profile: AgricultureMissionProfile;
  telemetry: TelemetrySnapshot | null;
  droneConnected: boolean;
  wsConnected: boolean;
}) {
  const t = (telemetry ?? {}) as Record<string, unknown>;
  const gps = nested(t, [
    "gps.fix_type",
    "gps_fix_type",
    "gps.satellites",
    "satellites",
  ]);
  const home = boolValue(
    nested(t, ["home.ready", "home_position_ready", "home"]),
  );
  const rows = [
    {
      label: "Saved field",
      state: fieldId != null,
      blocking: true,
      detail:
        fieldId != null ? `Field ${fieldId}` : "Save drawn boundary first",
    },
    {
      label: "GPS / home",
      state: gps != null && home !== false,
      blocking: true,
      detail:
        gps != null && home !== false
          ? "Telemetry present"
          : "Waiting for valid fix/home",
    },
    {
      label: "Camera / recording",
      state: droneConnected,
      blocking: true,
      detail: droneConnected ? "Vehicle connected" : "Vehicle not connected",
    },
    {
      label: "Telemetry stream",
      state: wsConnected,
      blocking: false,
      detail: wsConnected ? "Live" : "Polling fallback",
    },
    {
      label: "Calibration references",
      state:
        profile.sensor_inventory.every((sensor) => sensor === "rgb") ||
        profile.calibration_ids.length > 0,
      blocking: true,
      detail: profile.calibration_ids.length
        ? `${profile.calibration_ids.length} referenced; validity checked on ingest`
        : "RGB default",
    },
    {
      label: "Sensor requirements",
      state: profile.sensor_inventory.length > 0,
      blocking: true,
      detail: profile.sensor_inventory.join(", "),
    },
    {
      label: "Spectral / thermal readiness",
      state:
        profile.sensor_inventory.every((sensor) => sensor === "rgb") ||
        profile.calibration_ids.length > 0,
      blocking: true,
      detail: profile.sensor_inventory.some((sensor) => sensor !== "rgb")
        ? "Registered calibration required; outputs stay not measured until validated"
        : "Not required for RGB",
    },
    {
      label: "Coverage / battery",
      state: true,
      blocking: false,
      detail: "Validated by route preflight",
    },
    {
      label: "Weather",
      state: null,
      blocking: false,
      detail: "Check operator briefing",
    },
  ];
  return (
    <Stack
      spacing={1}
      sx={{ p: 1.5, border: 1, borderColor: "divider", borderRadius: 1 }}
    >
      <Typography variant="subtitle2">Agriculture launch preflight</Typography>
      {rows.map((row) => (
        <Stack key={row.label} direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            label={
              row.state === true
                ? "PASS"
                : row.state === false
                  ? row.blocking
                    ? "BLOCK"
                    : "WARN"
                  : "WARN"
            }
            color={
              row.state === true
                ? "success"
                : row.state === false && row.blocking
                  ? "error"
                  : "warning"
            }
          />
          <Typography variant="caption" sx={{ minWidth: 140 }}>
            {row.label}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {row.detail}
            {row.state === false && row.blocking ? " (blocking)" : ""}
          </Typography>
        </Stack>
      ))}
      <Divider />
      <Alert severity="info">
        Final GPS, home, obstacle, geofence, weather, and battery checks remain
        authoritative at mission start.
      </Alert>
    </Stack>
  );
}
