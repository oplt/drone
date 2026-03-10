import * as React from "react";
import { Box, Stack } from "@mui/material";
import { deriveTelemetry } from "../../../lib/deriveTelemetry";

function TelemetryBox({ label, value }: { label: string; value: string }) {
  return (
    <Box
      sx={{
        px: 1,
        py: 0.5,
        borderRadius: 1,
        bgcolor: "rgba(0,0,0,0.35)",
        color: "white",
        fontSize: 12,
        lineHeight: 1.2,
        minWidth: 88,
      }}
    >
      <div style={{ opacity: 0.85, fontSize: 10 }}>{label}</div>
      <div style={{ fontWeight: 600 }}>{value}</div>
    </Box>
  );
}

export function TelemetryHud({
  telemetry,
  sx,
}: {
  telemetry: any;
  sx?: any;
}) {
  const d = React.useMemo(() => deriveTelemetry(telemetry), [telemetry]);

  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{
        position: "absolute",
        top: 12,
        left: 12,
        zIndex: 2,
        flexWrap: "wrap",
        maxWidth: "calc(100% - 24px)",
        ...sx,
      }}
    >
      <TelemetryBox label="Status" value={d.flightStatus} />
      <TelemetryBox label="Mode" value={d.mode} />
      <TelemetryBox label="Speed" value={d.speed} />
      <TelemetryBox label="Alt" value={d.alt} />
      <TelemetryBox label="Wind" value={d.wind} />
      <TelemetryBox label="GPS" value={d.gpsStrength} />
      <TelemetryBox label="Battery" value={d.batteryHealth} />
      <TelemetryBox label="Failsafe" value={d.failsafe} />
      <TelemetryBox label="Heading" value={d.heading} />
    </Stack>
  );
}
