import { Box, Stack, Typography } from "@mui/material";
import { MissionFlightStatusPanel } from "../../mission-workflow";
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

      {isEventTriggeredPatrol && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Event Triggered Patrol
          </Typography>
          {eventLocation ? (
            <Typography variant="body2">
              Location: {eventLocation.lat.toFixed(6)}, {eventLocation.lon.toFixed(6)}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Using property polygon as response area
            </Typography>
          )}
          <Typography variant="body2">
            Track: {gridParams.track_target ? "yes" : "no"}
          </Typography>
        </Box>
      )}

      {missionStatus && (activeFlightId || waypoints.length > 0 || !!eventLocation) && (
        <MissionFlightStatusPanel missionStatus={missionStatus} />
      )}
    </>
  );
}
