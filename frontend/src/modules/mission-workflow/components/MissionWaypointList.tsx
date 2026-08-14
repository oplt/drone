import { Box, ListItemButton, Stack, Typography } from "@mui/material";
import type { Waypoint } from "../types";
import { legBearingDeg, legDistanceM } from "../utils/missionWaypointGeometry";

export function MissionWaypointList({
  waypoints,
  fallbackAltitude,
  selectedIndex = null,
  onSelect,
}: {
  waypoints: Waypoint[];
  fallbackAltitude: number;
  selectedIndex?: number | null;
  onSelect?: (index: number) => void;
}) {
  if (waypoints.length === 0) {
    return (
      <Box sx={{ mt: 3 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Waypoints
        </Typography>
        <Typography variant="body2" color="text.secondary">
          No waypoints yet. Draw a route or pick points on the map to build the
          plan.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Waypoints
      </Typography>
      <Stack spacing={0.5}>
        {waypoints.map((wp, idx) => {
          const prev = idx > 0 ? waypoints[idx - 1] : null;
          const distance = prev ? legDistanceM(prev, wp) : null;
          const bearing = prev ? legBearingDeg(prev, wp) : null;
          const selected = selectedIndex === idx;
          return (
            <ListItemButton
              key={`${wp.lat}-${wp.lon}-${idx}`}
              selected={selected}
              onClick={() => onSelect?.(idx)}
              sx={{
                borderRadius: 1,
                border: "1px solid",
                borderColor: selected ? "primary.main" : "divider",
                py: 1,
              }}
            >
              <Stack spacing={0.25} sx={{ width: "100%" }}>
                <Typography variant="body2" sx={{ fontWeight: selected ? 600 : 500 }}>
                  {idx + 1}. Lat {wp.lat.toFixed(6)}, Lon {wp.lon.toFixed(6)}, Alt{" "}
                  {wp.alt ?? fallbackAltitude}m
                </Typography>
                {distance != null && bearing != null ? (
                  <Typography variant="caption" color="text.secondary">
                    Leg {distance.toFixed(0)} m · bearing {bearing.toFixed(0)}°
                  </Typography>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    Start point
                  </Typography>
                )}
              </Stack>
            </ListItemButton>
          );
        })}
      </Stack>
    </Box>
  );
}
