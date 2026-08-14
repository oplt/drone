import DroneSvg from "../../../assets/Drone.svg?react";
import RoomIcon from "@mui/icons-material/Room";
import { Box, Stack, Typography } from "@mui/material";
import SvgIcon from "@mui/material/SvgIcon";
import { OverlayView, Polyline } from "@react-google-maps/api";
import type { RefObject } from "react";
import type { TerraDraw } from "terra-draw";
import {
  MissionMapViewport,
  RouteDrawControls,
  TerraDrawController,
  type RouteDrawMode,
  type RouteDrawToolMode,
  type TerraDrawEditorMode,
} from "../../maps";
import { CONTROLLED_FLIGHT_MAP_CONTAINER_STYLE } from "../controlledFlightViewConstants";
import type { LatLng } from "../../../shared/utils/extractLatLng";

type ControlledFlightMapColumnProps = {
  googleMap: google.maps.Map | null;
  terraDrawRef: RefObject<TerraDraw | null>;
  mapReady: boolean;
  loadingLocation: boolean;
  isLoaded: boolean;
  mapCenter: LatLng;
  mapZoom: number;
  mapOptions: google.maps.MapOptions;
  onMapClick: (event: google.maps.MapMouseEvent) => void;
  onMapLoad: (map: google.maps.Map) => void;
  onMapUnmount: () => void;
  onMapZoomChanged: () => void;
  onMapCenterChanged: () => void;
  terraDrawMode: TerraDrawEditorMode;
  setTerraDrawReady: (ready: boolean) => void;
  onMapError: (message: string) => void;
  drawMode: RouteDrawMode;
  onDrawModeChange: (mode: RouteDrawMode) => void;
  onToolModeChange: (mode: RouteDrawToolMode) => void;
  onUndo: () => void;
  drawnPoints: LatLng[];
  droneCenter: LatLng | null;
  heading: number | null;
  armed: boolean;
  userCenter: LatLng | null;
  activeFlightId: string | null;
};

export function ControlledFlightMapColumn({
  googleMap,
  terraDrawRef,
  mapReady,
  loadingLocation,
  isLoaded,
  mapCenter,
  mapZoom,
  mapOptions,
  onMapClick,
  onMapLoad,
  onMapUnmount,
  onMapZoomChanged,
  onMapCenterChanged,
  terraDrawMode,
  setTerraDrawReady,
  onMapError,
  drawMode,
  onDrawModeChange,
  onToolModeChange,
  onUndo,
  drawnPoints,
  droneCenter,
  heading,
  armed,
  userCenter,
  activeFlightId,
}: ControlledFlightMapColumnProps) {
  return (
    <Stack spacing={2}>
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
          map={mapReady ? googleMap : null}
          enabled
          mode={terraDrawMode}
          drawRef={terraDrawRef}
          onReadyChange={setTerraDrawReady}
          onSnapshotChange={() => {}}
          onError={onMapError}
        />
        <MissionMapViewport
          loadingLocation={loadingLocation}
          isLoaded={isLoaded}
          useCesium={false}
          googleMapProps={{
            mapContainerStyle: CONTROLLED_FLIGHT_MAP_CONTAINER_STYLE,
            center: mapCenter,
            zoom: mapZoom,
            onClick: onMapClick,
            onLoad: onMapLoad,
            onUnmount: onMapUnmount,
            onZoomChanged: onMapZoomChanged,
            onCenterChanged: onMapCenterChanged,
            options: mapOptions,
          }}
          googleWrapperSx={{ position: "relative" }}
          googleOverlay={
            <RouteDrawControls
              mode={drawMode}
              activeToolMode={
                terraDrawMode === "linestring"
                  ? "polyline"
                  : terraDrawMode === "select" || terraDrawMode === "static"
                    ? "none"
                    : terraDrawMode === "freehand"
                      ? "polygon"
                      : terraDrawMode
              }
              onModeChange={onDrawModeChange}
              onToolModeChange={onToolModeChange}
              onUndo={onUndo}
              hasWaypoints={drawnPoints.length > 0}
            />
          }
          cesiumMapProps={undefined}
          googleChildren={
            <>
              {drawnPoints.length >= 2 && (
                <Polyline
                  path={drawnPoints}
                  options={{
                    strokeColor: "#1976d2",
                    strokeOpacity: 0.8,
                    strokeWeight: 3,
                  }}
                />
              )}
              {droneCenter && (
                <OverlayView position={droneCenter} mapPaneName={OverlayView.OVERLAY_LAYER}>
                  <div
                    style={{
                      transform: `translate(-50%, -50%) rotate(${heading ?? 0}deg)`,
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
            </>
          }
        />
      </Box>
      <Typography variant="body2" sx={{ color: "text.secondary" }}>
        Map shows real-time drone position for situational awareness while flying manually.
      </Typography>
    </Stack>
  );
}
