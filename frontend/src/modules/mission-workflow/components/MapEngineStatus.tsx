import { Alert, Button, Stack } from "@mui/material";

export type MapEngineStatusProps = {
  mapEngine: string;
  /** Google Maps API key (only used when engine is google). */
  apiKey?: string;
  /** Google script load error. */
  loadError?: Error | undefined;
  /** Google Map ID for advanced markers. */
  mapId?: string;
  /** Non-Google engine failure message (WebGL / tiles / init). */
  engineError?: string | null;
  onSwitchEngine?: (engine: "google" | "cesium" | "leaflet" | "maplibre") => void;
};

/**
 * Shared operator-facing engine failure banner for all map engines.
 * Google key/load/Map ID checks preserve prior GoogleMapEngineAlerts behavior.
 */
export function MapEngineStatus({
  mapEngine,
  apiKey,
  loadError,
  mapId = "",
  engineError = null,
  onSwitchEngine,
}: MapEngineStatusProps) {
  const switchCta = onSwitchEngine ? (
    <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
      <Button size="small" variant="outlined" onClick={() => onSwitchEngine("maplibre")}>
        Switch to MapLibre
      </Button>
      <Button size="small" variant="outlined" onClick={() => onSwitchEngine("leaflet")}>
        Switch to Leaflet
      </Button>
    </Stack>
  ) : null;

  if (mapEngine === "google") {
    if (!apiKey) {
      return (
        <Alert severity="error" sx={{ mb: 2 }}>
          Missing Google Maps API Key. Set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in
          your .env file.
          {switchCta}
        </Alert>
      );
    }
    if (loadError) {
      return (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to load Google Maps. {loadError.message} Ensure the Maps
          JavaScript API is enabled, billing is active, and the key allows your
          domain.
          {switchCta}
        </Alert>
      );
    }
    if (!mapId) {
      return (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Google Maps Map ID is not set. Advanced markers require a Map ID. Set
          VITE_GOOGLE_MAPS_MAP_ID to remove this warning.
        </Alert>
      );
    }
    return null;
  }

  if (engineError) {
    const label =
      mapEngine === "cesium"
        ? "Cesium"
        : mapEngine === "leaflet"
          ? "Leaflet"
          : mapEngine === "maplibre"
            ? "MapLibre"
            : String(mapEngine);
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {label} map failed to load. {engineError} This is an engine failure, not
        missing mission data.
        {switchCta}
      </Alert>
    );
  }

  return null;
}

/** @deprecated Prefer MapEngineStatus — kept as a thin alias. */
export function GoogleMapEngineAlerts(props: MapEngineStatusProps) {
  return <MapEngineStatus {...props} />;
}
