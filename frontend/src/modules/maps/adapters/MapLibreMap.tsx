import { Box, Typography } from "@mui/material";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  type FlatDrawMode,
  type FlatDrawResult,
  type MapLibreMapProps,
} from "./maplibre/maplibreMapTypes";
import { useMapLibreMapSession } from "../hooks/useMapLibreMapSession";

export type { FlatDrawMode, FlatDrawResult, MapLibreMapProps };

export default function MapLibreMap({
  center,
  zoom,
  waypoints = [],
  droneCenter = null,
  userCenter = null,
  onPickLatLng,
  drawMode = "none",
  onDrawComplete,
  onBoundaryDrawStarted,
  onBoundaryDrawProgress,
  fieldBoundary = null,
  savedFields = [],
  selectedFieldId = null,
  onSavedFieldClick,
  onFieldBoundaryClick,
  drawnBoundarySelected = false,
  plannedRoute = null,
  exclusionZones = [],
  height = 400,
  focusRing = null,
  focusRequestToken,
  followEnabled = true,
  selectedWaypointIndex = null,
  onSelectWaypoint,
}: MapLibreMapProps) {
  const hostRef = useMapLibreMapSession({
    center,
    zoom,
    waypoints,
    droneCenter,
    userCenter,
    onPickLatLng,
    drawMode,
    onDrawComplete,
    onBoundaryDrawStarted,
    onBoundaryDrawProgress,
    fieldBoundary,
    savedFields,
    selectedFieldId,
    onSavedFieldClick,
    onFieldBoundaryClick,
    drawnBoundarySelected,
    plannedRoute,
    exclusionZones,
    focusRing,
    focusRequestToken,
    followEnabled,
    selectedWaypointIndex,
    onSelectWaypoint,
  });

  if (!Number.isFinite(center.lat) || !Number.isFinite(center.lng)) {
    return (
      <Box
        sx={{
          width: "100%",
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "background.paper",
        }}
      >
        <Typography variant="body2" color="text.secondary">
          Map center unavailable.
        </Typography>
      </Box>
    );
  }

  return (
    <div ref={hostRef} style={{ width: "100%", height, minHeight: 320 }} />
  );
}
