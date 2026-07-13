import { lazy, Suspense } from "react";
import type { ComponentProps } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";

const LeafletMap = lazy(() => import("./LeafletMap"));
type LeafletMapProps = ComponentProps<typeof LeafletMap>;

export default function LeafletMapLazy(props: LeafletMapProps) {
  return (
    <Suspense fallback={<Box sx={{ height: 400, display: "grid", placeItems: "center" }}><CircularProgress size={28} /><Typography variant="body2">Loading map…</Typography></Box>}>
      <LeafletMap {...props} />
    </Suspense>
  );
}
