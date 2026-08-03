import { Stack, Typography } from "@mui/material";
import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";

export function CoverageMapLayer({
  geojson,
}: {
  geojson: { features?: Array<Record<string, unknown>> };
}) {
  return (
    <Stack
      component="section"
      aria-labelledby="coverage-map-layer-heading"
      spacing={0.5}
    >
      <Typography id="coverage-map-layer-heading" variant="subtitle2">
        Coverage and reflight map
      </Typography>
      <AgricultureGeoJsonPreview geojson={geojson} />
    </Stack>
  );
}
