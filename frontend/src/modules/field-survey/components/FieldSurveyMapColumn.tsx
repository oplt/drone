import { useMemo, type ReactNode } from "react";
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
import { GroundOverlay, OverlayView, Polygon, Polyline } from "@react-google-maps/api";
import DroneSvg from "../../../assets/Drone.svg?react";
import type { FieldFeature, LonLat } from "../../fields";
import {
  CesiumViewControls,
  DEFAULT_MISSION_MAP_ENGINE,
  isFlatDrawToolSelected,
  MissionMapViewport,
  type TerraDrawToolMode,
} from "../../maps";
import { MissionMapFrameFooter } from "../../mission-workflow";
import { MissionVideoPanel } from "../../mission-runtime";
import type { useFieldSurveyPage } from "../hooks/useFieldSurveyPage";
import type { useFieldSurveyIrrigation } from "../hooks/useFieldSurveyIrrigation";

type PageVm = ReturnType<typeof useFieldSurveyPage>;
type IrrigationVm = ReturnType<typeof useFieldSurveyIrrigation>;

export function FieldSurveyMapColumn({
  vm,
  onSelectField,
  setupContent,
}: {
  vm: PageVm;
  onSelectField: (field: FieldFeature) => void;
  setupContent: ReactNode;
}) {
  const { apiBase, map, mission, irrigation, toAbsoluteAssetUrl, exclusionZones, fieldBorder } =
    vm;
  const savedFieldBoundaries = useMemo(
    () =>
      vm.fields.map((field) => ({
        id: field.id,
        name: field.name,
        ring: field.ring,
      })),
    [vm.fields],
  );
  const fieldFocusProps = {
    focusRing: map.fieldFocusRequest?.ring ?? null,
    focusRequestToken: map.fieldFocusRequest?.token,
  };

  return (
    <Stack sx={{ flex: 1, minHeight: 200 }} spacing={2}>
      <MissionVideoPanel
        title="Survey Camera"
        imgAlt="Survey camera stream"
        disconnectedMessage="Connect the drone to view the survey stream."
        frameHeight={360}
        apiBase={apiBase}
        streamKey={map.streamKey}
        videoToken={map.videoToken}
        startingVideo={map.startingVideo}
        videoError={map.videoError}
        videoRetryCount={map.videoRetryCount}
        droneConnected={vm.droneConnected}
        telemetry={vm.telemetry}
        missionLabel={vm.missionStatus?.mission_name ?? "Grid Mission"}
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
            ...fieldFocusProps,
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
            ...fieldFocusProps,
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
            ...fieldFocusProps,
          }}
          googleWrapperSx={{ position: "relative" }}
          googleChildren={
            <GoogleMapOverlays
              vm={vm}
              irrigation={irrigation}
              onSelectField={onSelectField}
              toAbsoluteAssetUrl={toAbsoluteAssetUrl}
            />
          }
          googleOverlay={
            <DrawToolsOverlay vm={vm} fieldBorder={fieldBorder} />
          }
        />
      </Box>

      <MissionMapFrameFooter
        setupTitle="Set up"
        setupSubtitle="Field boundary, grid parameters, and route preview"
        setupContent={setupContent}
        mapSelection={
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
        }
      />
    </Stack>
  );
}

function GoogleMapOverlays({
  vm,
  irrigation,
  onSelectField,
  toAbsoluteAssetUrl,
}: {
  vm: PageVm;
  irrigation: IrrigationVm;
  onSelectField: (field: FieldFeature) => void;
  toAbsoluteAssetUrl: (url: string) => string;
}) {
  const { map, mission, activeFlightId, fields } = vm;
  const { overlayBounds, irrigationLayer, irrigationZonePaths, irrigationZoneStyles, irrigationSummary } =
    irrigation;

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

      {overlayBounds?.north != null &&
        overlayBounds?.south != null &&
        overlayBounds?.east != null &&
        overlayBounds?.west != null &&
        irrigationLayer?.tile_manifest?.image_uri && (
          <GroundOverlay
            url={toAbsoluteAssetUrl(irrigationLayer.tile_manifest.image_uri)}
            bounds={{
              north: overlayBounds.north,
              south: overlayBounds.south,
              east: overlayBounds.east,
              west: overlayBounds.west,
            }}
            opacity={0.55}
          />
        )}

      {irrigationZonePaths.map(({ zone, path }) => {
        const style =
          irrigationZoneStyles[zone.type] ??
          ({
            fillColor: "#ef4444",
            strokeColor: "#991b1b",
            label: zone.type,
          } as const);
        return (
          <Polygon
            key={`irrigation-zone-${zone.id}`}
            paths={path}
            options={{
              clickable: true,
              fillColor: style.fillColor,
              fillOpacity: 0.28,
              strokeColor: style.strokeColor,
              strokeOpacity: 0.95,
              strokeWeight: 2,
              zIndex: 24,
            }}
          />
        );
      })}

      {(irrigationSummary?.inspection_points ?? []).map((point) => (
        <OverlayView
          key={`inspection-${point.id}`}
          position={{ lat: point.lat, lng: point.lon }}
          mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
        >
          <div
            style={{
              transform: "translate(-50%, -50%)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
            }}
          >
            <div
              style={{
                width: 18,
                height: 18,
                borderRadius: "999px",
                background: "#111827",
                color: "#ffffff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 10,
                fontWeight: 700,
                boxShadow: "0 4px 10px rgba(15,23,42,0.28)",
              }}
            >
              {Math.max(1, Math.round(point.priority * 9))}
            </div>
            <div
              style={{
                background: "rgba(255,255,255,0.96)",
                borderRadius: 4,
                padding: "2px 6px",
                fontSize: 10,
                whiteSpace: "nowrap",
                boxShadow: "0 2px 8px rgba(15,23,42,0.2)",
              }}
            >
              {point.label}
            </div>
          </div>
        </OverlayView>
      ))}

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
                    vm.setFieldBorder((prev) => {
                      if (!prev || prev.length <= 1) return null;
                      return prev.slice(0, -1) as LonLat[];
                    });
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
