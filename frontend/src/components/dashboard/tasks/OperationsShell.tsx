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
          background:
            "linear-gradient(135deg, hsla(174, 50%, 95%, 0.8), hsla(36, 40%, 96%, 0.9))",
          border: "1px solid hsla(174, 30%, 40%, 0.2)",
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
            <Typography variant="h3">{title}</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              {subtitle}
            </Typography>
          </Box>

          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              size="small"
              label={droneConnected ? "Drone online" : "Drone offline"}
              color={droneConnected ? "success" : "default"}
              variant={droneConnected ? "filled" : "outlined"}
            />
            <Chip
              size="small"
              label={wsConnected ? "Secure link" : "Link down"}
              color={wsConnected ? "success" : "default"}
              variant={wsConnected ? "filled" : "outlined"}
            />
          </Stack>
        </Stack>

        {!apiKey ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Missing Google Maps API Key. Please set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env file.
          </Alert>
        ) : loadError ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load Google Maps. {loadError.message} Ensure the Maps JavaScript API is enabled, billing is active,
            and the key allows your domain.
          </Alert>
        ) : !mapId ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Google Maps Map ID is not set. Advanced markers require a Map ID. Set VITE_GOOGLE_MAPS_MAP_ID to remove this warning.
          </Alert>
        ) : (
          children
        )}
      </Paper>
    </>
  );
}