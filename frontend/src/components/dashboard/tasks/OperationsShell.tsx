import * as React from "react";
import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";

export function OperationsShell({
  header,
  title,
  subtitle,
  droneConnected,
  wsConnected,
  apiKey,
  loadError,
  mapId,
  banner,
  children,
}: {
  header: React.ReactNode;
  title: string;
  subtitle: string;
  droneConnected: boolean;
  wsConnected: boolean;
  apiKey?: string;
  loadError?: Error | null;
  mapId?: string;
  banner?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      {header}
      <Paper
        sx={{
          width: "100%",
          p: 3,
          borderRadius: 3,
          border: "1px solid",
          borderColor: "divider",
          backgroundColor: "background.paper",
        }}
      >
        <Stack
          direction={{ xs: "column", md: "row" }}
          alignItems={{ xs: "flex-start", md: "center" }}
          justifyContent="space-between"
          sx={{ mb: 2 }}
          spacing={2}
        >
          <Box>
            <Typography variant="h4" sx={{ color: "text.primary" }}>{title}</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5 }}>
              {subtitle}
            </Typography>
          </Box>

          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              size="small"
              label={droneConnected ? "ONLINE" : "OFFLINE"}
              color={droneConnected ? "success" : "default"}
              variant="outlined"
            />
            <Chip
              size="small"
              label={wsConnected ? "LINK OK" : "LINK DOWN"}
              color={wsConnected ? "success" : "default"}
              variant="outlined"
            />
          </Stack>
        </Stack>

        {banner}

        {!apiKey ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Missing Google Maps API Key. Set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in .env.
          </Alert>
        ) : loadError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load Google Maps. {loadError.message}
          </Alert>
        ) : !mapId ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Map ID not set. Set VITE_GOOGLE_MAPS_MAP_ID for advanced markers.
          </Alert>
        ) : (
          children
        )}
      </Paper>
    </>
  );
}
