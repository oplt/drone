import DroneSvg from "../../../assets/Drone.svg?react";
import RoomIcon from "@mui/icons-material/Room";
import { Box } from "@mui/material";
import SvgIcon from "@mui/material/SvgIcon";
import { OverlayView, Polyline } from "@react-google-maps/api";
import type { RefObject } from "react";
import type { TerraDraw } from "terra-draw";
import {
  CesiumViewControls,
  DEFAULT_MISSION_MAP_ENGINE,
  MissionMapViewport,
  RouteDrawControls,
  TerraDrawController,
  type CesiumViewMode,
  type MissionMapEngine,
  type RouteDrawMode,
  type RouteDrawToolMode,
  type TerraDrawEditorMode,
  type TerraDrawFeature,
} from "../../maps";
import type { LonLat } from "../../fields";
import {
  MapEngineSelectionOverlay,
  MapShapeActionPopover,
} from "../../mission-workflow";
import { ANIMAL_FARM_MAP_CONTAINER_STYLE } from "../animalFarmPageConstants";
import type { AnimalFarmWaypoint } from "../animalFarmPageTypes";
import type { HerdLatestPos } from "../types";
import type { LatLng } from "../../../shared/utils/extractLatLng";

type AnimalFarmMapColumnProps = {
  googleMap: google.maps.Map | null;
  terraDrawRef: RefObject<TerraDraw | null>;
  mapReady: boolean;
  mapEngine: MissionMapEngine;
  useCesium: boolean;
  cesiumViewMode: CesiumViewMode;
  onCesiumViewModeChange: (mode: CesiumViewMode) => void;
  onMapEngineChange: (engine: MissionMapEngine) => void;
  loadingLocation: boolean;
  isLoaded: boolean;
  mapCenter: LatLng;
  mapZoom: number;
  mapOptions: google.maps.MapOptions;
  onMapClick: (event: google.maps.MapMouseEvent) => void;
  onMapLoad: (map: google.maps.Map) => void;
  onMapZoomChanged: () => void;
  terraDrawMode: TerraDrawEditorMode;
  setTerraDrawReady: (ready: boolean) => void;
  onTerraSnapshotChange: (snapshot: TerraDrawFeature[]) => void;
  onTerraChangeEvent: (event: string, snapshot: TerraDrawFeature[]) => void;
  onTerraSelectionChange: (selectedFeatureId: string | number | null) => void;
  onMapError: (message: string) => void;
  drawMode: RouteDrawMode;
  onDrawModeChange: (mode: RouteDrawMode) => void;
  onToolModeChange: (mode: RouteDrawToolMode) => void;
  onUndo: () => void;
  terraDrawFeatureCount: number;
  waypoints: AnimalFarmWaypoint[];
  farmBorder: LonLat[] | null;
  droneCenter: LatLng | null;
  heading: number | null;
  armed: boolean;
  userCenter: LatLng | null;
  polylinePath: Array<{ lat: number; lng: number }>;
  latestPositions: HerdLatestPos[];
  activeFlightId: string | null;
  shapePromptOpen: boolean;
  farmBorderName: string;
  savingFarmBorder: boolean;
  onFarmBorderNameChange: (name: string) => void;
  onFarmBorderSave: () => void;
  onShapePromptDismiss: () => void;
  farmBorderDraw: {
    onBoundaryDrawStarted?: () => void;
    onBoundaryDrawProgress: (ring: LonLat[]) => void;
  };
  onRouteDrawComplete: (result: {
    type: "point" | "polyline" | "polygon";
    coordinates: [number, number] | [number, number][];
  }) => void;
};

export function AnimalFarmMapColumn({
  googleMap,
  terraDrawRef,
  mapReady,
  mapEngine,
  useCesium,
  cesiumViewMode,
  onCesiumViewModeChange,
  onMapEngineChange,
  loadingLocation,
  isLoaded,
  mapCenter,
  mapZoom,
  mapOptions,
  onMapClick,
  onMapLoad,
  onMapZoomChanged,
  terraDrawMode,
  setTerraDrawReady,
  onTerraSnapshotChange,
  onTerraChangeEvent,
  onTerraSelectionChange,
  onMapError,
  drawMode,
  onDrawModeChange,
  onToolModeChange,
  onUndo,
  terraDrawFeatureCount,
  waypoints,
  farmBorder,
  droneCenter,
  heading,
  armed,
  userCenter,
  polylinePath,
  latestPositions,
  activeFlightId,
  shapePromptOpen,
  farmBorderName,
  savingFarmBorder,
  onFarmBorderNameChange,
  onFarmBorderSave,
  onShapePromptDismiss,
  farmBorderDraw,
  onRouteDrawComplete,
}: AnimalFarmMapColumnProps) {
  return (
    <Box
      sx={{
        borderRadius: 2,
        overflow: "hidden",
        border: "1px solid",
        borderColor: "divider",
        backgroundColor: "background.paper",
      }}
    >
      <TerraDrawController
        map={mapReady && mapEngine === "google" ? googleMap : null}
        enabled={mapEngine === "google"}
        mode={terraDrawMode}
        drawRef={terraDrawRef}
        onReadyChange={setTerraDrawReady}
        onSnapshotChange={onTerraSnapshotChange}
        onChangeEvent={onTerraChangeEvent}
        onSelectionChange={onTerraSelectionChange}
        onError={onMapError}
      />
      <MissionMapViewport
        loadingLocation={loadingLocation}
        isLoaded={isLoaded}
        useCesium={useCesium}
        mapEngine={mapEngine}
        googleMapProps={{
          mapContainerStyle: ANIMAL_FARM_MAP_CONTAINER_STYLE,
          center: mapCenter,
          zoom: mapZoom,
          onClick: onMapClick,
          onLoad: onMapLoad,
          onZoomChanged: onMapZoomChanged,
          options: mapOptions,
        }}
        cesiumMapProps={{
          center: mapCenter,
          zoom: mapZoom,
          viewMode: cesiumViewMode,
          waypoints,
          fieldBoundary: farmBorder && farmBorder.length >= 3 ? farmBorder : null,
          droneCenter,
          headingDeg: typeof heading === "number" ? heading : null,
          drawMode,
          onDrawComplete: onRouteDrawComplete,
          onBoundaryDrawStarted: farmBorderDraw.onBoundaryDrawStarted,
          onBoundaryDrawProgress: farmBorderDraw.onBoundaryDrawProgress,
        }}
        leafletMapProps={{
          center: mapCenter,
          zoom: mapZoom,
          waypoints,
          droneCenter,
          userCenter,
          drawMode,
          onDrawComplete: onRouteDrawComplete,
          onBoundaryDrawStarted: farmBorderDraw.onBoundaryDrawStarted,
          onBoundaryDrawProgress: farmBorderDraw.onBoundaryDrawProgress,
          height: 400,
        }}
        mapLibreMapProps={{
          center: mapCenter,
          zoom: mapZoom,
          waypoints,
          droneCenter,
          userCenter,
          drawMode,
          onDrawComplete: onRouteDrawComplete,
          onBoundaryDrawStarted: farmBorderDraw.onBoundaryDrawStarted,
          onBoundaryDrawProgress: farmBorderDraw.onBoundaryDrawProgress,
          height: 400,
        }}
        googleWrapperSx={{ position: "relative" }}
        googleOverlay={
          <>
            <MapShapeActionPopover
              open={shapePromptOpen}
              variant="farm-border"
              name={farmBorderName}
              saving={savingFarmBorder}
              onNameChange={onFarmBorderNameChange}
              onSave={onFarmBorderSave}
              onDismiss={onShapePromptDismiss}
            />
            <RouteDrawControls
              mode={drawMode}
              activeToolMode={
                mapEngine === "google"
                  ? terraDrawMode === "linestring"
                    ? "polyline"
                    : terraDrawMode === "select" || terraDrawMode === "static"
                      ? "none"
                      : terraDrawMode === "freehand"
                        ? "polygon"
                        : terraDrawMode
                  : undefined
              }
              onModeChange={onDrawModeChange}
              onToolModeChange={onToolModeChange}
              onUndo={onUndo}
              hasWaypoints={waypoints.length > 0 || terraDrawFeatureCount > 0}
            />
            <MapEngineSelectionOverlay>
              <CesiumViewControls
                useCesium={useCesium}
                onUseCesiumChange={(next: boolean) =>
                  onMapEngineChange(next ? "cesium" : DEFAULT_MISSION_MAP_ENGINE)
                }
                mapEngine={mapEngine}
                onMapEngineChange={onMapEngineChange}
                viewMode={cesiumViewMode}
                onViewModeChange={onCesiumViewModeChange}
              />
            </MapEngineSelectionOverlay>
          </>
        }
        googleChildren={
          <>
            {droneCenter && (
              <OverlayView position={droneCenter} mapPaneName={OverlayView.OVERLAY_LAYER}>
                <div
                  style={{
                    transform: `translate(-50%, -50%) rotate(${typeof heading === "number" ? heading : 0}deg)`,
                    transformOrigin: "center",
                    color: armed ? "#1976d2" : "#9aa0a6",
                    zIndex: 9999,
                  }}
                >
                  <SvgIcon
                    component={DroneSvg}
                    inheritViewBox
                    sx={{
                      width: 40,
                      height: 40,
                      filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.35))",
                    }}
                  />
                  {activeFlightId && (
                    <div
                      style={{
                        position: "absolute",
                        top: "-28px",
                        left: "50%",
                        transform: "translateX(-50%)",
                        background: "white",
                        padding: "2px 6px",
                        borderRadius: "3px",
                        fontSize: "10px",
                        whiteSpace: "nowrap",
                        boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
                      }}
                    >
                      Flight: {activeFlightId.substring(0, 8)}...
                    </div>
                  )}
                </div>
              </OverlayView>
            )}
            {userCenter && (
              <OverlayView position={userCenter} mapPaneName={OverlayView.OVERLAY_LAYER}>
                <div style={{ transform: "translate(-50%, -50%)", color: "#4caf50" }}>
                  <RoomIcon fontSize="large" />
                </div>
              </OverlayView>
            )}
            {waypoints.length >= 2 && (
              <Polyline
                path={polylinePath}
                options={{
                  strokeColor: "#1976d2",
                  strokeOpacity: 0.8,
                  strokeWeight: 3,
                }}
              />
            )}
            {latestPositions.map((position) => (
              <OverlayView
                key={position.animal_id}
                position={{ lat: position.lat, lng: position.lon }}
                mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
              >
                <Box
                  sx={{
                    transform: "translate(-50%, -100%)",
                    display: "flex",
                    alignItems: "center",
                    gap: 0.5,
                    background: "rgba(0,0,0,0.55)",
                    color: "white",
                    px: 1,
                    py: 0.25,
                    borderRadius: 1,
                    fontSize: 12,
                  }}
                >
                  <RoomIcon fontSize="small" />
                  <span>{position.animal_name || position.collar_id}</span>
                </Box>
              </OverlayView>
            ))}
          </>
        }
      />
    </Box>
  );
}
