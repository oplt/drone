import { Box, Stack, Typography } from "@mui/material";
import type { MissionStatus } from "../types";

export function MissionFlightStatusPanel({
  missionStatus,
}: {
  missionStatus: MissionStatus;
}) {
  return (
    <Box sx={{ mt: 2, p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: "bold", mb: 1 }}>
        Flight Status
      </Typography>
      <Stack spacing={0.5}>
        {missionStatus.flight_id && (
          <Typography variant="caption" component="div">
            Flight ID: {missionStatus.flight_id}
          </Typography>
        )}
        {missionStatus.mission_name && (
          <Typography variant="caption" component="div">
            Plan: {missionStatus.mission_name}
          </Typography>
        )}
        <Typography variant="caption" component="div">
          Telemetry:{" "}
          {missionStatus.telemetry?.running ? (
            <span style={{ color: "green" }}>Running</span>
          ) : (
            <span style={{ color: "red" }}>Stopped</span>
          )}
        </Typography>
        {missionStatus.telemetry?.active_connections !== undefined && (
          <Typography variant="caption" component="div">
            WS Connections: {missionStatus.telemetry.active_connections}
          </Typography>
        )}
        <Typography variant="caption" component="div">
          Drone Connected:{" "}
          {missionStatus.orchestrator?.drone_connected ? (
            <span style={{ color: "green" }}>Yes</span>
          ) : (
            <span style={{ color: "red" }}>No</span>
          )}
        </Typography>
      </Stack>
    </Box>
  );
}
