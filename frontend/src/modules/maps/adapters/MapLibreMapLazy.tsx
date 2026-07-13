import { lazy, Suspense } from "react";
import type { ComponentProps } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";

const MapLibreMap = lazy(() => import("./MapLibreMap"));
type MapLibreMapProps = ComponentProps<typeof MapLibreMap>;

export default function MapLibreMapLazy(props: MapLibreMapProps) {
  return (
    <Suspense fallback={<Box sx={{ height: 400, display: "grid", placeItems: "center" }}><CircularProgress size={28} /><Typography variant="body2">Loading map…</Typography></Box>}>
      <MapLibreMap {...props} />
    </Suspense>
  );
}
