import { Box, Button, Stack, TextField, Typography } from "@mui/material";
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import type { TerraDraw } from "terra-draw";
import {
  GoogleMapsContext,
  MissionMapViewport,
  RouteDrawControls,
  TerraDrawController,
  type RouteDrawMode,
  type TerraDrawFeature,
} from "../../maps";
import type { AgricultureLonLat } from "../geometry";

type PickMode = "takeoff" | "landing" | null;

function openRing(ring: AgricultureLonLat[] | null): AgricultureLonLat[] {
  if (!ring?.length) return [];
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (ring.length > 1 && first[0] === last[0] && first[1] === last[1]) {
    return ring.slice(0, -1);
  }
  return [...ring];
}

async function geocodeQuery(query: string): Promise<google.maps.LatLngLiteral | null> {
  const maps = typeof window !== "undefined" ? window.google?.maps : undefined;
  if (!maps?.Geocoder) return null;
  const geocoder = new maps.Geocoder();
  try {
    const response = await geocoder.geocode({ address: query });
    const location = response.results[0]?.geometry?.location;
    if (!location) return null;
    return { lat: location.lat(), lng: location.lng() };
  } catch {
    return null;
  }
}

export function AgricultureGeometryMapEditor({
  boundary,
  exclusionZones = [],
  onBoundaryChange,
  onExclusionZone,
  onPointPick,
  height = 360,
  focusRequestToken: externalFocusToken = 0,
}: {
  boundary: AgricultureLonLat[] | null;
  exclusionZones?: AgricultureLonLat[][];
  onBoundaryChange?: (ring: AgricultureLonLat[]) => void;
  onExclusionZone?: (ring: AgricultureLonLat[]) => void;
  onPointPick?: (kind: Exclude<PickMode, null>, point: AgricultureLonLat) => void;
  height?: number;
  /** Bump when an imported boundary should fit the map (wizard / parent). */
  focusRequestToken?: number;
}) {
  const [mode, setMode] = useState<RouteDrawMode>("none");
  const { isLoaded } = useContext(GoogleMapsContext);
  const [googleMap, setGoogleMap] = useState<google.maps.Map | null>(null);
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const [, setTerraReady] = useState(false);
  const [drawingTarget, setDrawingTarget] = useState<"boundary" | "exclusion">("boundary");
  const [pickMode, setPickMode] = useState<PickMode>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [mapCenter, setMapCenter] = useState(() =>
    boundary?.[0]
      ? { lng: boundary[0][0], lat: boundary[0][1] }
      : { lng: 4.3517, lat: 50.8503 },
  );
  const [localFocusToken, setLocalFocusToken] = useState(0);
  const focusRequestToken = externalFocusToken + localFocusToken;
  const focusRing = boundary && boundary.length >= 2 ? boundary : null;

  const startPolygon = (target: "boundary" | "exclusion") => {
    setPickMode(null);
    setDrawingTarget(target);
    setMode("polygon");
  };
  const acceptPolygon = useCallback((ring: AgricultureLonLat[]) => {
    if (drawingTarget === "boundary") onBoundaryChange?.(ring);
    else onExclusionZone?.(ring);
    setMode("none");
  }, [drawingTarget, onBoundaryChange, onExclusionZone]);
  const handleTerraSnapshot = useCallback((snapshot: TerraDrawFeature[]) => {
    const polygon = [...snapshot].reverse().find((feature) => feature.geometry?.type === "Polygon");
    const coordinates = polygon?.geometry?.coordinates;
    if (!Array.isArray(coordinates) || !Array.isArray(coordinates[0])) return;
    acceptPolygon(coordinates[0] as AgricultureLonLat[]);
  }, [acceptPolygon]);

  const undoLastVertex = useCallback(() => {
    if (!onBoundaryChange) return;
    const open = openRing(boundary);
    if (!open.length) return;
    const next = open.slice(0, -1);
    onBoundaryChange(next);
  }, [boundary, onBoundaryChange]);

  const clearBoundary = useCallback(() => {
    if (!onBoundaryChange) return;
    onBoundaryChange([]);
    setMode("none");
  }, [onBoundaryChange]);

  const fitToBoundary = useCallback(() => {
    if (!boundary || boundary.length < 2) return;
    setLocalFocusToken((token) => token + 1);
  }, [boundary]);

  useEffect(() => {
    if (!googleMap || focusRequestToken === 0 || !focusRing?.length || !window.google?.maps) {
      return;
    }
    const bounds = new google.maps.LatLngBounds();
    for (const [lng, lat] of openRing(focusRing)) {
      bounds.extend({ lat, lng });
    }
    if (!bounds.isEmpty()) {
      googleMap.fitBounds(bounds);
    }
  }, [focusRequestToken, focusRing, googleMap]);

  const runLocationSearch = async () => {
    const query = searchQuery.trim();
    if (!query) return;
    if (!isLoaded || !window.google?.maps?.Geocoder) {
      setSearchMessage("Location search needs Google Maps. Drawing and import still work.");
      return;
    }
    setSearchMessage(null);
    const location = await geocodeQuery(query);
    if (!location) {
      setSearchMessage("No matching place found. Try a clearer address or locality.");
      return;
    }
    setMapCenter({ lng: location.lng, lat: location.lat });
    if (googleMap) {
      googleMap.panTo(location);
      googleMap.setZoom(16);
    }
    setSearchMessage(null);
  };

  const hasVertices = openRing(boundary).length > 0;

  return (
    <Stack spacing={1}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "flex-start" }}>
        <TextField
          size="small"
          label="Search location"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void runLocationSearch();
            }
          }}
          helperText={searchMessage ?? "Address, place, or farm locality (Google Maps)."}
          fullWidth
          inputProps={{ "aria-label": "Search location" }}
        />
        <Button
          sx={{ minHeight: 44, flexShrink: 0 }}
          variant="outlined"
          onClick={() => void runLocationSearch()}
        >
          Search
        </Button>
      </Stack>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {onBoundaryChange ? (
          <Button sx={{ minHeight: 44 }} variant={drawingTarget === "boundary" && mode === "polygon" ? "contained" : "outlined"} onClick={() => startPolygon("boundary")}>
            Draw field boundary
          </Button>
        ) : null}
        {onExclusionZone ? (
          <Button sx={{ minHeight: 44 }} variant={drawingTarget === "exclusion" && mode === "polygon" ? "contained" : "outlined"} onClick={() => startPolygon("exclusion")}>
            Draw exclusion zone
          </Button>
        ) : null}
        {onPointPick ? (
          <>
            <Button sx={{ minHeight: 44 }} variant={pickMode === "takeoff" ? "contained" : "outlined"} onClick={() => { setMode("none"); setPickMode("takeoff"); }}>
              Pick take-off
            </Button>
            <Button sx={{ minHeight: 44 }} variant={pickMode === "landing" ? "contained" : "outlined"} onClick={() => { setMode("none"); setPickMode("landing"); }}>
              Pick landing
            </Button>
          </>
        ) : null}
        {onBoundaryChange ? (
          <>
            <Button sx={{ minHeight: 44 }} variant="outlined" disabled={!hasVertices} onClick={undoLastVertex}>
              Undo last point
            </Button>
            <Button sx={{ minHeight: 44 }} variant="outlined" color="warning" disabled={!hasVertices} onClick={clearBoundary}>
              Clear boundary
            </Button>
            <Button sx={{ minHeight: 44 }} variant="outlined" disabled={!boundary || boundary.length < 2} onClick={fitToBoundary}>
              Fit to boundary
            </Button>
          </>
        ) : null}
      </Stack>
      <Typography variant="caption" color="text.secondary">
        {pickMode ? `Select the ${pickMode} point on the map.` : mode === "polygon" ? "Click boundary points, then double-click the final point." : "Use the controls to draw or edit map geometry."}
      </Typography>
      <Box sx={{ position: "relative", borderRadius: 1, overflow: "hidden" }}>
        <MissionMapViewport
          loadingLocation={false}
          isLoaded={isLoaded}
          mapEngine={isLoaded ? "google" : "maplibre"}
          googleMapProps={{
            center: mapCenter,
            zoom: 15,
            mapContainerStyle: { width: "100%", height },
            onLoad: setGoogleMap,
            onUnmount: () => setGoogleMap(null),
            onClick: (event) => {
              if (!pickMode || !onPointPick || !event.latLng) return;
              onPointPick(pickMode, [event.latLng.lng(), event.latLng.lat()]);
              setPickMode(null);
            },
          }}
          mapLibreMapProps={{
            center: mapCenter,
            zoom: 15,
            height,
            drawMode: mode,
            fieldBoundary: boundary,
            exclusionZones,
            focusRing,
            focusRequestToken: focusRequestToken || undefined,
            onPickLatLng: (point) => {
              if (!pickMode || !onPointPick) return;
              onPointPick(pickMode, [point.lng, point.lat]);
              setPickMode(null);
            },
            onDrawComplete: (result) => {
              if (result.type !== "polygon") return;
              acceptPolygon(result.coordinates);
            },
          }}
          googleChildren={
            <TerraDrawController
              map={googleMap}
              enabled={isLoaded}
              mode={mode === "polygon" ? "polygon" : "select"}
              drawRef={terraDrawRef}
              onReadyChange={setTerraReady}
              onSnapshotChange={handleTerraSnapshot}
            />
          }
          googleOverlay={
            <RouteDrawControls
              mode={mode}
              onModeChange={setMode}
              onUndo={undoLastVertex}
              deleteLabel="Undo last boundary point"
              hasWaypoints={hasVertices}
            />
          }
          googleWrapperSx={{ height }}
        />
      </Box>
    </Stack>
  );
}
