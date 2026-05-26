import { lazy, Suspense } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import type { ComponentProps } from "react";

const CesiumMap = lazy(() => import("./CesiumMap"));

type CesiumMapProps = ComponentProps<typeof CesiumMap>;

/**
 * Lazy boundary for the Cesium engine. Import this from MissionMapViewport so
 * Cesium/Resium are not pulled into routes that never render a map.
 */
export default function CesiumMapLazy(props: CesiumMapProps) {
  return (
    <Suspense
      fallback={
        <Box
          sx={{
            width: "100%",
            height: 400,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            bgcolor: "background.paper",
          }}
        >
          <CircularProgress size={28} />
          <Typography sx={{ ml: 2 }} variant="body2">
            Loading 3D map…
          </Typography>
        </Box>
      }
    >
      <CesiumMap {...props} />
    </Suspense>
  );
}
