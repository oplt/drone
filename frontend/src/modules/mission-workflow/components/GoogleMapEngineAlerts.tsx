import { Alert } from "@mui/material";

export function GoogleMapEngineAlerts({
  mapEngine,
  apiKey,
  loadError,
  mapId,
}: {
  mapEngine: string;
  apiKey: string | undefined;
  loadError: Error | undefined;
  mapId: string;
}) {
  if (mapEngine !== "google") return null;

  if (!apiKey) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        Missing Google Maps API Key. Please set
        VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env file.
      </Alert>
    );
  }

  if (loadError) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        Failed to load Google Maps. {loadError.message} Ensure the Maps
        JavaScript API is enabled, billing is active, and the key allows
        your domain.
      </Alert>
    );
  }

  if (!mapId) {
    return (
      <Alert severity="warning" sx={{ mb: 2 }}>
        Google Maps Map ID is not set. Advanced markers require a Map ID.
        Set VITE_GOOGLE_MAPS_MAP_ID to remove this warning.
      </Alert>
    );
  }

  return null;
}
