import { Alert, Box, CircularProgress, Stack, Typography } from "@mui/material";
import maplibregl, {
  type Map as MapLibreMap,
  type MapMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgricultureMapAccessibleList } from "./agriculture-analysis-map/AgricultureMapAccessibleList";
import { AgricultureMapControls } from "./agriculture-analysis-map/AgricultureMapControls";
import {
  accessibleMapFeatures,
  allMapPositions,
  availableMapLayers,
  buildAgricultureMapData,
  featureCenter,
} from "./agriculture-analysis-map/data";
import {
  AGRICULTURE_MAP_LAYERS,
  DEFAULT_AGRICULTURE_MAP_VISIBILITY,
  addAgricultureMapLayers,
  applyAgricultureMapVisibility,
  handleAgricultureMapClick,
  updateAgricultureMapData,
} from "./agriculture-analysis-map/layers";
import type {
  AgricultureAnalysisMapProps,
  AgricultureMapLayerKey,
} from "./agriculture-analysis-map/types";
import { fitAgricultureMap } from "./agriculture-analysis-map/camera";

const MAP_STYLE_URL = "https://tiles.stadiamaps.com/styles/alidade_smooth.json";

export function AgricultureAnalysisMap({
  observations,
  fieldBoundary,
  flightPath,
  severityAreas,
  interventionZones,
  temporalChanges,
  selectedId,
  onSelect,
  initialVisibility,
  contextStatus,
  height = 440,
}: AgricultureAnalysisMapProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelect);
  const data = useMemo(
    () =>
      buildAgricultureMapData({
        observations,
        fieldBoundary,
        flightPath,
        severityAreas,
        interventionZones,
        temporalChanges,
        selectedId,
      }),
    [
      fieldBoundary,
      flightPath,
      interventionZones,
      temporalChanges,
      observations,
      selectedId,
      severityAreas,
    ],
  );
  const dataRef = useRef(data);
  const coordinates = useMemo(() => allMapPositions(data), [data]);
  const accessible = useMemo(() => accessibleMapFeatures(observations, temporalChanges, interventionZones), [interventionZones, observations, temporalChanges]);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [visibility, setVisibility] = useState({
    ...DEFAULT_AGRICULTURE_MAP_VISIBILITY,
    ...initialVisibility,
  });
  const visibilityRef = useRef(visibility);
  useEffect(() => {
    dataRef.current = data;
    onSelectRef.current = onSelect;
    visibilityRef.current = visibility;
  }, [data, onSelect, visibility]);
  const available = useMemo(() => availableMapLayers(data), [data]);
  const hasData = coordinates.length > 0;

  useEffect(() => {
    if (!hostRef.current || mapRef.current || !hasData) return;
    try {
      const map = new maplibregl.Map({
        container: hostRef.current,
        center: allMapPositions(dataRef.current)[0] as [number, number],
        zoom: 15,
        style: MAP_STYLE_URL,
      });
      mapRef.current = map;
      map.dragRotate.disable();
      map.touchZoomRotate.disableRotation();
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
      map.once("load", () => {
        addAgricultureMapLayers(map, dataRef.current);
        applyAgricultureMapVisibility(map, visibilityRef.current);
        fitAgricultureMap(map, allMapPositions(dataRef.current));
        map.getCanvas().setAttribute("aria-label", "Interactive agriculture analysis map");
        setMapReady(true);
      });
      map.on("click", (event: MapMouseEvent) => {
        void handleAgricultureMapClick(map, event.point, onSelectRef.current).catch(
          () => undefined,
        );
      });
      map.on("mousemove", (event: MapMouseEvent) => {
        if (!map.isStyleLoaded()) return;
        const interactive = map.queryRenderedFeatures(event.point, {
          layers: [
            AGRICULTURE_MAP_LAYERS.cluster,
            AGRICULTURE_MAP_LAYERS.observationPoint,
            AGRICULTURE_MAP_LAYERS.observationShapeFill,
            AGRICULTURE_MAP_LAYERS.severityFill,
            AGRICULTURE_MAP_LAYERS.temporalFill,
            AGRICULTURE_MAP_LAYERS.zoneFill,
          ],
        });
        map.getCanvas().style.cursor = interactive.length ? "pointer" : "";
      });
      return () => {
        map.remove();
        mapRef.current = null;
      };
    } catch {
      queueMicrotask(() =>
        setMapError("The interactive map could not start on this device."),
      );
    }
  }, [hasData]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    updateAgricultureMapData(mapRef.current, data);
  }, [data, mapReady]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    applyAgricultureMapVisibility(mapRef.current, visibility);
  }, [mapReady, visibility]);

  useEffect(() => {
    const map = mapRef.current;
    const selected = data.selection.features[0];
    if (!mapReady || !map || !selected) return;
    const center = featureCenter(selected);
    if (center) {
      map.easeTo({
        center: center as [number, number],
        zoom: Math.max(map.getZoom(), 16),
        duration: 350,
      });
    }
  }, [data.selection, mapReady]);

  const toggleLayer = (key: AgricultureMapLayerKey) => {
    setVisibility((current) => ({ ...current, [key]: !current[key] }));
  };
  const fitToData = useCallback(() => {
    if (mapRef.current) {
      fitAgricultureMap(mapRef.current, allMapPositions(dataRef.current));
    }
  }, []);

  return (
    <Stack component="section" aria-label="Agriculture analysis map" spacing={1}>
      <AgricultureMapControls
        visibility={visibility}
        available={available}
        contextStatus={contextStatus}
        onToggle={toggleLayer}
        onFit={fitToData}
      />
      {mapError ? <Alert severity="warning">{mapError}</Alert> : null}
      {!hasData ? (
        <Alert severity="info">
          No georeferenced map data is available. Unresolved observations remain
          in the review list.
        </Alert>
      ) : (
        <Box sx={{ position: "relative" }}>
          {!mapReady ? (
            <Stack
              role="status"
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ position: "absolute", zIndex: 1, top: 12, left: 12, p: 1, bgcolor: "background.paper", border: 1, borderColor: "divider" }}
            >
              <CircularProgress size={16} />
              <Typography variant="caption">Loading interactive map…</Typography>
            </Stack>
          ) : null}
          <Box
            ref={hostRef}
            role="region"
            aria-label="Interactive agriculture analysis map"
            sx={{ height, minHeight: 320, border: 1, borderColor: "divider", overflow: "hidden" }}
          />
        </Box>
      )}
      <AgricultureMapAccessibleList
        features={accessible}
        selectedId={selectedId}
        onSelect={onSelect}
      />
    </Stack>
  );
}

export type {
  AgricultureAnalysisMapProps,
  AgricultureMapContextStatus,
  AgricultureMapGeoJson,
  AgricultureMapLayerVisibility,
} from "./agriculture-analysis-map/types";
