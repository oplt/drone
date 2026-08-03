import { Box, Stack, Typography } from "@mui/material";

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function AgricultureLiveMap({ telemetry, connection }: { telemetry: Record<string, unknown> | null; connection: string }) {
  const position = (telemetry?.position ?? {}) as Record<string, unknown>;
  const lat = number(position.lat ?? position.latitude);
  const lon = number(position.lon ?? position.lng ?? position.longitude);
  const hasPosition = lat !== null && lon !== null;
  return <Stack component="section" aria-labelledby="agri-live-map-heading" spacing={0.5}>
    <Typography id="agri-live-map-heading" variant="subtitle2">Live flight map</Typography>
    <Box component="svg" viewBox="0 0 400 180" role="img" aria-label={hasPosition ? `Drone position ${lat?.toFixed(5)}, ${lon?.toFixed(5)}` : "Drone position unavailable"} sx={{ width: "100%", minHeight: 150, bgcolor: "#eef4e9", border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
      <rect width="400" height="180" fill="#eef4e9" />
      <path d="M20 140 C100 90 160 150 230 80 S330 55 380 25" fill="none" stroke="#8aa77a" strokeWidth="3" strokeDasharray="6 5" />
      {hasPosition ? <circle cx="230" cy="80" r="9" fill="#1565c0" stroke="#fff" strokeWidth="3" /> : null}
      <text x="16" y="24" fontSize="12" fill="#263238">{hasPosition ? "Current drone position" : "Waiting for georeferenced telemetry"}</text>
    </Box>
    <Typography variant="caption" color="text.secondary" aria-live="polite">{hasPosition ? `GPS ${lat?.toFixed(6)}, ${lon?.toFixed(6)} · link ${connection}` : `Last-known position unavailable · link ${connection}`}</Typography>
  </Stack>;
}
