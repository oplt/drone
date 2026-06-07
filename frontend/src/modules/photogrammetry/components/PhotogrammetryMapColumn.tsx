import { useMemo } from "react";
import { Box, IconButton, Paper, Stack, Tooltip } from "@mui/material";
import SvgIcon from "@mui/material/SvgIcon";
import RoomIcon from "@mui/icons-material/Room";
import PentagonOutlinedIcon from "@mui/icons-material/PentagonOutlined";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import CropSquareOutlinedIcon from "@mui/icons-material/CropSquareOutlined";
import RadioButtonUncheckedOutlinedIcon from "@mui/icons-material/RadioButtonUncheckedOutlined";
import PanToolAltOutlinedIcon from "@mui/icons-material/PanToolAltOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import { OverlayView, Polygon, Polyline } from "@react-google-maps/api";
import DroneSvg from "../../../assets/Drone.svg?react";
import type { FieldFeature, LonLat } from "../../fields";
import {
  CesiumViewControls,
  DEFAULT_MISSION_MAP_ENGINE,
  isFlatDrawToolSelected,
  MissionMapViewport,
  type TerraDrawToolMode,
} from "../../maps";
import { MissionVideoPanel } from "../../mission-runtime";
import type { usePhotogrammetryPage } from "../hooks/usePhotogrammetryPage";

type PageVm = ReturnType<typeof usePhotogrammetryPage>;

export function PhotogrammetryMapColumn({
  vm,
  onSelectField,
}: {
  vm: PageVm;
  onSelectField: (field: FieldFeature) => void;
}) {
  const { apiBase, map, mission, exclusionZones, fieldBorder } = vm;
  const savedFieldBoundaries = useMemo(
    () =>
      vm.fields.map((field) => ({
        id: field.id,
        name: field.name,
        ring: field.ring,
      })),
    [vm.fields],
  );

  return (
    <Stack sx={{ flex: 1, minHeight: 200 }} spacing={2}>
      <MissionVideoPanel
        title="PhotoGrammetry Camera"
        imgAlt="Photogrammetry camera stream"
        disconnectedMessage="Connect the drone to view the photogrammetry stream."
        apiBase={apiBase}
        streamKey={map.streamKey}
        videoToken={map.videoToken}
        startingVideo={map.startingVideo}
        videoError={map.videoError}
        videoRetryCount={map.videoRetryCount}
        droneConnected={vm.droneConnected}
        telemetry={vm.telemetry}
        onVideoError={map.handleVideoError}
        onVideoLoad={map.handleVideoLoad}
        onRetry={map.handleVideoRetry}
      />
      <Box
        sx={{
          borderRadius: 2,
          overflow: "hidden",
          border: "1px solid",
          borderColor: "divider",
          backgroundColor: "background.paper",
        }}
      >
        <MissionMapViewport
          loadingLocation={map.loadingLocation}
          isLoaded={map.isLoaded}
          useCesium={map.useCesium}
          mapEngine={map.mapEngine}
          googleMapProps={{
            mapContainerStyle: map.containerStyle,
            center: map.mapCenter,
            zoom: map.mapZoom,
            onClick: map.onMapClick,
            onLoad: map.onMapLoad,
            onUnmount: map.onMapUnmount,
            onZoomChanged: map.onMapZoomChanged,
            onCenterChanged: map.onMapCenterChanged,
            options: map.mapOptions,
          }}
          cesiumMapProps={{
            center: map.mapCenter,
            zoom: vm.cesiumZoom,
            viewMode: map.cesiumViewMode,
            waypoints: mission.waypoints,
            fieldBoundary: map.cesiumFieldBoundary,
            plannedRoute: mission.cesiumPlannedRoute,
            exclusionZones,
            fieldTilesetUrl: vm.fieldTilesetUrl,
            droneCenter: map.droneCenter,
            headingDeg: typeof map.heading === "number" ? map.heading : null,
            onPickLatLng: mission.handleCesiumPick,
            drawMode: mission.drawMode,
            onDrawComplete: map.handleCesiumDrawComplete,
          }}
          leafletMapProps={{
            center: map.mapCenter,
            zoom: map.mapZoom,
            waypoints: mission.waypoints,
            fieldBoundary: map.cesiumFieldBoundary,
            savedFields: savedFieldBoundaries,
            selectedFieldId: vm.selectedFieldId,
            onSavedFieldClick: vm.handleSavedFieldSelect,
            plannedRoute: mission.cesiumPlannedRoute,
            exclusionZones,
            droneCenter: map.droneCenter,
            userCenter: map.userCenter,
            onPickLatLng: mission.handleCesiumPick,
            drawMode: mission.drawMode,
            onDrawComplete: map.handleCesiumDrawComplete,
            height: 400,
          }}
          mapLibreMapProps={{
            center: map.mapCenter,
            zoom: map.mapZoom,
            waypoints: mission.waypoints,
            fieldBoundary: map.cesiumFieldBoundary,
            savedFields: savedFieldBoundaries,
            selectedFieldId: vm.selectedFieldId,
            onSavedFieldClick: vm.handleSavedFieldSelect,
            plannedRoute: mission.cesiumPlannedRoute,
            exclusionZones,
            droneCenter: map.droneCenter,
            userCenter: map.userCenter,
            onPickLatLng: mission.handleCesiumPick,
            drawMode: mission.drawMode,
            onDrawComplete: map.handleCesiumDrawComplete,
            height: 400,
          }}
          googleWrapperSx={{ position: "relative" }}
          googleChildren={
            <GoogleMapOverlays vm={vm} onSelectField={onSelectField} />
          }
          googleOverlay={<DrawToolsOverlay vm={vm} fieldBorder={fieldBorder} />}
        />
      </Box>

      <Paper
        variant="outlined"
        sx={{
          p: 1.5,
          borderRadius: 2,
          flexShrink: 0,
          alignSelf: { xs: "stretch", lg: "flex-start" },
        }}
      >
        <CesiumViewControls
          useCesium={map.useCesium}
          onUseCesiumChange={(next) =>
            map.handleMapEngineChange(next ? "cesium" : DEFAULT_MISSION_MAP_ENGINE)
          }
          mapEngine={map.mapEngine}
          onMapEngineChange={map.handleMapEngineChange}
          viewMode={map.cesiumViewMode}
          onViewModeChange={map.setCesiumViewMode}
        />
      </Paper>
    </Stack>
  );
}

function GoogleMapOverlays({
  vm,
  onSelectField,
}: {
  vm: PageVm;
  onSelectField: (field: FieldFeature) => void;
}) {
  const { map, mission, activeFlightId, fields } = vm;

  return (
    <>
      {fields.map((f) => (
        <Polygon
          key={f.id}
          paths={f.path}
          onClick={() => onSelectField(f)}
          options={{
            clickable: true,
            fillColor: "#000000",
            fillOpacity: 0,
            strokeOpacity: 0.85,
            strokeWeight: vm.selectedFieldId === f.id ? 3 : 2,
            zIndex: vm.selectedFieldId === f.id ? 15 : 5,
          }}
        />
      ))}

      {map.droneCenter && (
        <OverlayView
          position={map.droneCenter}
          mapPaneName={OverlayView.OVERLAY_LAYER}
        >
          <div
            style={{
              transform: `translate(-50%, -50%) rotate(${
                typeof map.heading === "number" ? map.heading : 0
              }deg)`,
              transformOrigin: "center",
              color: map.armed ? "#1976d2" : "#9aa0a6",
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

      {map.userCenter && (
        <OverlayView
          position={map.userCenter}
          mapPaneName={OverlayView.OVERLAY_LAYER}
        >
          <div
            style={{
              transform: "translate(-50%, -50%)",
              color: "#4caf50",
            }}
          >
            <RoomIcon fontSize="large" />
          </div>
        </OverlayView>
      )}

      {mission.gridPreview && mission.gridPreview.length >= 2 && (
        <>
          {mission.gridPreview.slice(0, -1).map((wp, i) =>
            mission.gridPreviewMask?.[i] ? (
              <Polyline
                key={`work-${i}`}
                path={[
                  { lat: wp.lat, lng: wp.lon },
                  {
                    lat: mission.gridPreview![i + 1].lat,
                    lng: mission.gridPreview![i + 1].lon,
                  },
                ]}
                options={{
                  strokeColor: "#2e7d32",
                  strokeOpacity: 0.85,
                  strokeWeight: 2,
                }}
              />
            ) : (
              <Polyline
                key={`turn-${i}`}
                path={[
                  { lat: wp.lat, lng: wp.lon },
                  {
                    lat: mission.gridPreview![i + 1].lat,
                    lng: mission.gridPreview![i + 1].lon,
                  },
                ]}
                options={{
                  strokeColor: "#f57c00",
                  strokeOpacity: 0.6,
                  strokeWeight: 1.5,
                  icons: [
                    {
                      icon: {
                        path: "M 0,-1 0,1",
                        strokeOpacity: 1,
                        scale: 2,
                      },
                      offset: "0",
                      repeat: "10px",
                    },
                  ],
                }}
              />
            )
          )}
        </>
      )}

      {map.terraDrawMode === "static" && mission.waypoints.length >= 2 && (
        <Polyline
          path={mission.polylinePath}
          options={{
            strokeColor: "#1976d2",
            strokeOpacity: 0.8,
            strokeWeight: 3,
          }}
        />
      )}
    </>
  );
}

function DrawToolsOverlay({
  vm,
  fieldBorder,
}: {
  vm: PageVm;
  fieldBorder: LonLat[] | null;
}) {
  const { map, mission, borderEditor } = vm;

  return (
    <Paper
      elevation={2}
      sx={{
        position: "absolute",
        left: 10,
        top: "50%",
        transform: "translateY(-50%)",
        zIndex: 1300,
        pointerEvents: "auto",
        p: 0.5,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
      }}
    >
      <Stack direction="column" spacing={0.5}>
        {[
          {
            mode: "polygon",
            label: "Polygon",
            icon: <PentagonOutlinedIcon fontSize="small" />,
          },
          {
            mode: "linestring",
            label: "Line",
            icon: <ShowChartIcon fontSize="small" />,
          },
          {
            mode: "point",
            label: "Point",
            icon: <PlaceOutlinedIcon fontSize="small" />,
          },
          {
            mode: "rectangle",
            label: "Rectangle",
            icon: <CropSquareOutlinedIcon fontSize="small" />,
          },
          {
            mode: "circle",
            label: "Circle",
            icon: <RadioButtonUncheckedOutlinedIcon fontSize="small" />,
          },
          {
            mode: "select",
            label: "Select",
            icon: <PanToolAltOutlinedIcon fontSize="small" />,
          },
        ].map((tool) => {
          const selected =
            map.mapEngine !== "google"
              ? isFlatDrawToolSelected(mission.drawMode, tool.mode as TerraDrawToolMode)
              : map.terraDrawMode === tool.mode;
          return (
            <Tooltip key={tool.mode} title={tool.label} placement="right" arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={() =>
                    map.handleDrawingToolSelection(tool.mode as TerraDrawToolMode)
                  }
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    bgcolor: selected ? "primary.main" : "background.paper",
                    color: selected ? "primary.contrastText" : "text.primary",
                    "&:hover": {
                      bgcolor: selected ? "primary.dark" : "action.hover",
                    },
                  }}
                >
                  {tool.icon}
                </IconButton>
              </span>
            </Tooltip>
          );
        })}

        <Tooltip title="Delete latest drawing" placement="right" arrow>
          <span>
            <IconButton
              size="small"
              color="error"
              onClick={() => {
                if (map.mapEngine !== "google") {
                  if (mission.drawMode !== "none") {
                    mission.setDrawMode("none");
                    return;
                  }
                  if (fieldBorder && fieldBorder.length > 0) {
                    vm.setFieldBorder(null);
                    return;
                  }
                  mission.setWaypoints((prev) => prev.slice(0, -1));
                  return;
                }

                if (!map.terraDrawRef.current) return;
                const snapshot = map.terraDrawRef.current.getSnapshot();
                const latestFeature = [...snapshot]
                  .reverse()
                  .find((f) => borderEditor.isRemovableUserDrawingFeature(f));
                if (!latestFeature) return;

                map.terraDrawRef.current.removeFeatures([String(latestFeature.id)]);

                const remaining = map.terraDrawRef.current.getSnapshot();
                borderEditor.syncFieldBorderFromSnapshot(remaining);
              }}
              disabled={
                map.mapEngine !== "google"
                  ? mission.drawMode === "none" &&
                    (!fieldBorder || fieldBorder.length === 0) &&
                    mission.waypoints.length === 0
                  : !map.terraDrawReady
              }
              sx={{
                border: "1px solid",
                borderColor: "divider",
                bgcolor: "background.paper",
                "&:hover": { bgcolor: "action.hover" },
              }}
            >
              <DeleteOutlineOutlinedIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    </Paper>
  );
}
