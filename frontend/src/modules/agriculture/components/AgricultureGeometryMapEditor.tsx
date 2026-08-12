import { Box, Button, Stack, Typography } from "@mui/material";
import { useCallback, useContext, useRef, useState } from "react";
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

export function AgricultureGeometryMapEditor({
  boundary,
  exclusionZones = [],
  onBoundaryChange,
  onExclusionZone,
  onPointPick,
  height = 360,
}: {
  boundary: AgricultureLonLat[] | null;
  exclusionZones?: AgricultureLonLat[][];
  onBoundaryChange?: (ring: AgricultureLonLat[]) => void;
  onExclusionZone?: (ring: AgricultureLonLat[]) => void;
  onPointPick?: (kind: Exclude<PickMode, null>, point: AgricultureLonLat) => void;
  height?: number;
}) {
  const [mode, setMode] = useState<RouteDrawMode>("none");
  const { isLoaded } = useContext(GoogleMapsContext);
  const [googleMap, setGoogleMap] = useState<google.maps.Map | null>(null);
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const [, setTerraReady] = useState(false);
  const [drawingTarget, setDrawingTarget] = useState<"boundary" | "exclusion">("boundary");
  const [pickMode, setPickMode] = useState<PickMode>(null);
  const center = boundary?.[0]
    ? { lng: boundary[0][0], lat: boundary[0][1] }
    : { lng: 4.3517, lat: 50.8503 };

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

  return (
    <Stack spacing={1}>
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
            center,
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
            center,
            zoom: 15,
            height,
            drawMode: mode,
            fieldBoundary: boundary,
            exclusionZones,
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
              onUndo={() => {
                if (drawingTarget === "boundary") onBoundaryChange?.([]);
              }}
              hasWaypoints={Boolean(boundary?.length)}
            />
          }
          googleWrapperSx={{ height }}
        />
      </Box>
    </Stack>
  );
}
