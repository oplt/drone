import { Box, Stack, Typography } from "@mui/material";
import type { Waypoint } from "../types";

export function MissionWaypointList({
  waypoints,
  fallbackAltitude,
}: {
  waypoints: Waypoint[];
  fallbackAltitude: number;
}) {
  if (waypoints.length === 0) return null;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Waypoints
      </Typography>
      <Stack spacing={1}>
        {waypoints.map((wp, idx) => (
          <Typography key={idx} variant="body2">
            {idx + 1}. Lat: {wp.lat.toFixed(6)}, Lon: {wp.lon.toFixed(6)}, Alt:{" "}
            {wp.alt ?? fallbackAltitude}m
          </Typography>
        ))}
      </Stack>
    </Box>
  );
}
