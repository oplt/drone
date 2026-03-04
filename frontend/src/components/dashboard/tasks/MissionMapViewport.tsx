import type { ComponentProps, ReactNode } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import { GoogleMap } from "@react-google-maps/api";
import CesiumMap from "../../../utils/CesiumMap";

type GoogleMapProps = ComponentProps<typeof GoogleMap>;
type CesiumMapProps = ComponentProps<typeof CesiumMap>;

export function MissionMapViewport({
  loadingLocation,
  isLoaded,
  useCesium = false,
  loadingLocationLabel = "Loading your location...",
  loadingMapLabel = "Loading map...",
  googleMapProps,
  cesiumMapProps,
  googleChildren,
  googleWrapperSx,
  googleOverlay,
}: {
  loadingLocation: boolean;
  isLoaded: boolean;
  useCesium?: boolean;
  loadingLocationLabel?: string;
  loadingMapLabel?: string;
  googleMapProps: GoogleMapProps;
  cesiumMapProps?: CesiumMapProps;
  googleChildren?: ReactNode;
  googleWrapperSx?: any;
  googleOverlay?: ReactNode;
}) {
  if (loadingLocation) {
    return (
      <Box
        sx={{
          width: "100%",
          height: 400,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "hsla(36, 30%, 96%, 0.7)",
        }}
      >
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>{loadingLocationLabel}</Typography>
      </Box>
    );
  }

  if (!isLoaded) {
    return (
      <Box
        sx={{
          width: "100%",
          height: 400,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "hsla(36, 30%, 96%, 0.7)",
        }}
      >
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>{loadingMapLabel}</Typography>
      </Box>
    );
  }

  if (useCesium && cesiumMapProps) {
    const cesiumNode = <CesiumMap {...cesiumMapProps} />;
    if (!googleWrapperSx && !googleOverlay) return cesiumNode;

    return (
      <Box sx={googleWrapperSx}>
        {cesiumNode}
        {googleOverlay}
      </Box>
    );
  }

  const mapNode = <GoogleMap {...googleMapProps}>{googleChildren}</GoogleMap>;
  if (!googleWrapperSx && !googleOverlay) return mapNode;

  return (
    <Box sx={googleWrapperSx}>
      {mapNode}
      {googleOverlay}
    </Box>
  );
}
