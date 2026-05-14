import { useEffect, useMemo, useState } from "react";
import type { ComponentProps, ReactNode } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import { GoogleMap } from "@react-google-maps/api";
import CesiumMap from "../../../utils/CesiumMap";
import LeafletMap from "../../LeafletMap";
import MapLibreMap from "../../MapLibreMap";

type GoogleMapProps = ComponentProps<typeof GoogleMap>;
type CesiumMapProps = ComponentProps<typeof CesiumMap>;
type LeafletMapProps = ComponentProps<typeof LeafletMap>;
type MapLibreMapProps = ComponentProps<typeof MapLibreMap>;
export type MissionMapEngine = "google" | "cesium" | "leaflet" | "maplibre";

export function MissionMapViewport({
  loadingLocation,
  isLoaded,
  useCesium = false,
  mapEngine,
  loadingLocationLabel = "Loading your location...",
  loadingMapLabel = "Loading map...",
  googleMapProps,
  cesiumMapProps,
  leafletMapProps,
  mapLibreMapProps,
  googleChildren,
  googleWrapperSx,
  googleOverlay,
}: {
  loadingLocation: boolean;
  isLoaded: boolean;
  useCesium?: boolean;
  mapEngine?: MissionMapEngine;
  loadingLocationLabel?: string;
  loadingMapLabel?: string;
  googleMapProps: GoogleMapProps;
  cesiumMapProps?: CesiumMapProps;
  leafletMapProps?: LeafletMapProps;
  mapLibreMapProps?: MapLibreMapProps;
  googleChildren?: ReactNode;
  googleWrapperSx?: any;
  googleOverlay?: ReactNode;
}) {
  const [internalEngine, setInternalEngine] = useState<MissionMapEngine>(
    useCesium ? "cesium" : "google",
  );

  useEffect(() => {
    if (mapEngine) return;
    setInternalEngine((current) => {
      if (useCesium) return "cesium";
      return current === "cesium" ? "google" : current;
    });
  }, [mapEngine, useCesium]);

  useEffect(() => {
    if (mapEngine) return;
    const handleEngineChange = (event: Event) => {
      const next = (event as CustomEvent<MissionMapEngine>).detail;
      if (next === "google" || next === "cesium" || next === "leaflet" || next === "maplibre") {
        setInternalEngine(next);
      }
    };
    window.addEventListener("mission-map-engine-change", handleEngineChange);
    return () => {
      window.removeEventListener("mission-map-engine-change", handleEngineChange);
    };
  }, [mapEngine]);

  const selectedEngine = mapEngine ?? internalEngine;
  const fallbackFlatMapProps = useMemo(() => {
    const rawCenter = googleMapProps.center as any;
    const center =
      typeof rawCenter?.lat === "function" && typeof rawCenter?.lng === "function"
        ? { lat: rawCenter.lat(), lng: rawCenter.lng() }
        : rawCenter;
    const containerStyle = googleMapProps.mapContainerStyle as any;
    const height = containerStyle?.height ?? 400;

    return {
      center,
      zoom: googleMapProps.zoom ?? 12,
      height,
      onPickLatLng: (p: { lat: number; lng: number }) => {
        googleMapProps.onClick?.({
          latLng: {
            lat: () => p.lat,
            lng: () => p.lng,
          },
        } as google.maps.MapMouseEvent);
      },
    };
  }, [googleMapProps]);

  if (loadingLocation) {
    return (
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
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>{loadingLocationLabel}</Typography>
      </Box>
    );
  }

  if (selectedEngine === "google" && !isLoaded) {
    return (
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
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>{loadingMapLabel}</Typography>
      </Box>
    );
  }

  if (selectedEngine === "cesium" && cesiumMapProps) {
    const cesiumNode = <CesiumMap {...cesiumMapProps} />;
    if (!googleWrapperSx && !googleOverlay) return cesiumNode;

    return (
      <Box sx={googleWrapperSx}>
        {cesiumNode}
        {googleOverlay}
      </Box>
    );
  }

  if (selectedEngine === "leaflet" && leafletMapProps) {
    const leafletNode = <LeafletMap {...leafletMapProps} />;
    if (!googleWrapperSx && !googleOverlay) return leafletNode;

    return (
      <Box sx={googleWrapperSx}>
        {leafletNode}
        {googleOverlay}
      </Box>
    );
  }

  if (selectedEngine === "leaflet" && fallbackFlatMapProps.center) {
    const leafletNode = <LeafletMap {...fallbackFlatMapProps} />;
    if (!googleWrapperSx && !googleOverlay) return leafletNode;

    return (
      <Box sx={googleWrapperSx}>
        {leafletNode}
        {googleOverlay}
      </Box>
    );
  }

  if (selectedEngine === "maplibre" && mapLibreMapProps) {
    const mapLibreNode = <MapLibreMap {...mapLibreMapProps} />;
    if (!googleWrapperSx && !googleOverlay) return mapLibreNode;

    return (
      <Box sx={googleWrapperSx}>
        {mapLibreNode}
        {googleOverlay}
      </Box>
    );
  }

  if (selectedEngine === "maplibre" && fallbackFlatMapProps.center) {
    const mapLibreNode = <MapLibreMap {...fallbackFlatMapProps} />;
    if (!googleWrapperSx && !googleOverlay) return mapLibreNode;

    return (
      <Box sx={googleWrapperSx}>
        {mapLibreNode}
        {googleOverlay}
      </Box>
    );
  }

  const mapNode = <GoogleMap {...googleMapProps}>{googleChildren}</GoogleMap>;
  if (!googleWrapperSx && !googleOverlay) return mapNode;

  return (
    <Box sx={googleWrapperSx}>
      {mapNode}
      {googleOverlay}
    </Box>
  );
}
