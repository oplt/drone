import { Alert, Box, Button, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Live geo readout with explicit path to the real mission map.
 * Decorative SVG maps are intentionally not used here.
 */
export function AgricultureLiveMap({
  telemetry,
  connection,
  fieldId,
}: {
  telemetry: Record<string, unknown> | null;
  connection: string;
  fieldId?: string | number | null;
}) {
  const position = (telemetry?.position ?? {}) as Record<string, unknown>;
  const lat = number(position.lat ?? position.latitude);
  const lon = number(position.lon ?? position.lng ?? position.longitude);
  const hasPosition = lat !== null && lon !== null;
  const missionMapTo = fieldId
    ? `/dashboard/field`
    : "/dashboard/field";

  return (
    <Stack
      component="section"
      aria-labelledby="agri-live-map-heading"
      spacing={1}
      sx={{
        p: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        bgcolor: "background.paper",
      }}
    >
      <Typography id="agri-live-map-heading" variant="subtitle2">
        Live position
      </Typography>
      <Box
        role="status"
        aria-live="polite"
        sx={{
          minHeight: 72,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 0.5,
        }}
      >
        {hasPosition ? (
          <Typography variant="body2" sx={{ fontFamily: "ui-monospace, monospace" }}>
            GPS {lat!.toFixed(6)}, {lon!.toFixed(6)}
          </Typography>
        ) : (
          <Alert severity="info" sx={{ py: 0.5 }}>
            Waiting for georeferenced telemetry. Link: {connection}.
          </Alert>
        )}
        <Typography variant="caption" color="text.secondary">
          Link {connection}. For planning geometry and layers, open the mission
          map — this panel is position status only.
        </Typography>
      </Box>
      <Button
        component={RouterLink}
        to={missionMapTo}
        size="small"
        variant="outlined"
      >
        Open mission map
      </Button>
    </Stack>
  );
}
