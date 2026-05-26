import { Box, Stack, Typography } from "@mui/material";
import type { PrivatePatrolMissionStatus } from "../types";
import type { usePrivatePatrolMission } from "../hooks/usePrivatePatrolMission";

type MissionVm = ReturnType<typeof usePrivatePatrolMission>;

export function PrivatePatrolStatusSections({
  mission,
  missionStatus,
  activeFlightId,
}: {
  mission: MissionVm;
  missionStatus: PrivatePatrolMissionStatus | null;
  activeFlightId: string | null;
}) {
  const {
    waypoints,
    alt,
    isWaypointPatrol,
    isEventTriggeredPatrol,
    eventLocation,
    gridParams,
  } = mission;

  return (
    <>
      {isWaypointPatrol && waypoints.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Key Points
          </Typography>
          <Stack spacing={1}>
            {waypoints.map((wp, idx) => (
              <Typography key={idx} variant="body2">
                {idx + 1}. Lat: {wp.lat.toFixed(6)}, Lon: {wp.lon.toFixed(6)}, Alt:{" "}
                {wp.alt ?? alt}m
              </Typography>
            ))}
          </Stack>
        </Box>
      )}

      {isEventTriggeredPatrol && eventLocation && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Trigger Event
          </Typography>
          <Typography variant="body2">
            Location: {eventLocation.lat.toFixed(6)}, {eventLocation.lon.toFixed(6)}
          </Typography>
          <Typography variant="body2">
            Trigger: {gridParams.trigger_type} | Track:{" "}
            {gridParams.track_target ? "yes" : "no"} | Stream:{" "}
            {gridParams.auto_stream_video ? "yes" : "no"}
          </Typography>
        </Box>
      )}

      {missionStatus && (activeFlightId || waypoints.length > 0 || !!eventLocation) && (
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
      )}
    </>
  );
}
