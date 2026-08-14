import { Alert, Box, Divider, Paper, Stack, Typography } from "@mui/material";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import { MissionStatusChips, MissionVideoPanel } from "../../mission-runtime";
import { MissionSurveyCameraSection } from "../../mission-workflow";
import { VideoAnalysisPanel } from "../../video-analysis";
import type { AnimalFarmPageSession } from "../hooks/useAnimalFarmPageSession";
import { AnimalFarmMapColumn } from "./AnimalFarmMapColumn";
import { AnimalFarmRouteSetupPanel } from "./AnimalFarmRouteSetupPanel";
import { AnimalFarmWaypointsStatusSection } from "./AnimalFarmWaypointsStatusSection";

type AnimalFarmPageMainSectionProps = {
  session: AnimalFarmPageSession;
};

export function AnimalFarmPageMainSection({ session }: AnimalFarmPageMainSectionProps) {
  const {
    apiBase,
    apiKey,
    mapId,
    videoToken,
    isLoaded,
    loadError,
    errors,
    addError,
    dismissError,
    clearErrors,
    altitude,
    runtime,
    droneCenter,
    commandMetrics,
    drawing,
    map,
    missionPlanner,
    herds,
    video,
    userCenter,
    loadingLocation,
  } = session;

  const heading = typeof commandMetrics.heading === "number" ? commandMetrics.heading : null;

  return (
    <Paper
      sx={{
        width: "100%",
        p: 3,
        borderRadius: 3,
        backgroundColor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack
        direction={{ xs: "column", md: "row" }}
        alignItems={{ xs: "flex-start", md: "center" }}
        justifyContent="space-between"
        sx={{ mb: 2 }}
        spacing={2}
      >
        <Box>
          <Typography variant="h3">Field Operations</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Configure field routes, stream telemetry, and monitor imagery in real time.
          </Typography>
        </Box>
        <MissionStatusChips
          droneConnected={runtime.droneConnected}
          wsConnected={runtime.wsConnected}
        />
      </Stack>

      <ErrorAlerts errors={errors} onDismiss={dismissError} onClearAll={clearErrors} />

      {!apiKey ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          Missing Google Maps API Key. Please set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env
          file.
        </Alert>
      ) : loadError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to load Google Maps. {loadError.message} Ensure the Maps JavaScript API is enabled,
          billing is active, and the key allows your domain (for local dev: http://localhost:5173/*).
        </Alert>
      ) : !mapId ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Google Maps Map ID is not set. Advanced markers require a Map ID. Set VITE_GOOGLE_MAPS_MAP_ID
          to remove this warning.
        </Alert>
      ) : (
        <>
          <Box sx={{ mb: 3 }}>
            <MissionSurveyCameraSection
              setupSubtitle="Field plan, altitude, and route waypoints"
              video={
                <MissionVideoPanel
                  embedded
                  title="Survey Camera"
                  imgAlt="Survey camera stream"
                  disconnectedMessage="Connect the drone to view the survey stream."
                  frameHeight={360}
                  apiBase={apiBase}
                  streamKey={video.streamKey}
                  videoToken={videoToken}
                  startingVideo={video.startingVideo}
                  videoError={video.videoError}
                  videoRetryCount={video.videoRetryCount}
                  droneConnected={runtime.droneConnected}
                  telemetry={runtime.telemetry}
                  onVideoError={video.handleVideoError}
                  onVideoLoad={video.handleVideoLoad}
                  onRetry={video.handleVideoRetry}
                />
              }
              map={
                <AnimalFarmMapColumn
                  googleMap={map.googleMap}
                  terraDrawRef={drawing.terraDrawRef}
                  mapReady={map.mapReady}
                  mapEngine={map.mapEngine}
                  useCesium={map.useCesium}
                  cesiumViewMode={map.cesiumViewMode}
                  onCesiumViewModeChange={map.setCesiumViewMode}
                  onMapEngineChange={map.handleMapEngineChange}
                  loadingLocation={loadingLocation}
                  isLoaded={isLoaded}
                  mapCenter={map.mapCenter}
                  mapZoom={map.mapZoom}
                  mapOptions={map.mapOptions}
                  onMapClick={drawing.onMapClick}
                  onMapLoad={map.onMapLoad}
                  onMapZoomChanged={map.onMapZoomChanged}
                  terraDrawMode={drawing.terraDrawMode}
                  setTerraDrawReady={drawing.setTerraDrawReady}
                  onTerraSnapshotChange={drawing.handleTerraSnapshotChange}
                  onTerraChangeEvent={drawing.shapePrompt.handleChangeEvent}
                  onTerraSelectionChange={drawing.shapePrompt.handleSelectionChange}
                  onMapError={addError}
                  drawMode={drawing.drawMode}
                  onDrawModeChange={drawing.setDrawMode}
                  onToolModeChange={drawing.handleRouteToolModeChange}
                  onUndo={drawing.undo}
                  terraDrawFeatureCount={drawing.terraDrawFeatureCount}
                  waypoints={drawing.waypoints}
                  farmBorder={drawing.farmBorder}
                  droneCenter={droneCenter}
                  heading={heading}
                  armed={commandMetrics.armed}
                  userCenter={userCenter}
                  polylinePath={drawing.polylinePath}
                  latestPositions={herds.latestPositions}
                  activeFlightId={runtime.activeFlightId}
                  shapePromptOpen={drawing.shapePrompt.open}
                  farmBorderName={drawing.farmBorderName}
                  savingFarmBorder={drawing.savingFarmBorder}
                  onFarmBorderNameChange={drawing.setFarmBorderName}
                  onFarmBorderSave={() => void drawing.handleFarmBorderSave()}
                  onShapePromptDismiss={drawing.shapePrompt.closePrompt}
                  farmBorderDraw={drawing.farmBorderDraw}
                  onRouteDrawComplete={drawing.handleRouteDrawComplete}
                />
              }
              setup={
                <AnimalFarmRouteSetupPanel
                  name={missionPlanner.name}
                  onNameChange={missionPlanner.setName}
                  altInput={altitude.altInput}
                  onAltitudeInputChange={altitude.handleAltitudeInputChange}
                  onAltitudeBlur={altitude.normalizeAltitude}
                  waypointCount={drawing.waypoints.length}
                  sending={missionPlanner.sending}
                  activeFlightId={runtime.activeFlightId}
                  activeMissionName={runtime.missionStatus?.mission_name}
                  onUndo={drawing.undo}
                  onClear={drawing.clearWaypoints}
                  onSendMission={() => void missionPlanner.sendMission()}
                />
              }
              videoAnalysis={
                <VideoAnalysisPanel
                  embedded
                  missionId={runtime.activeFlightId}
                  flightActive={Boolean(runtime.activeFlightId)}
                />
              }
            />
          </Box>
          <Divider sx={{ mb: 2 }} />
          <AnimalFarmWaypointsStatusSection
            waypoints={drawing.waypoints}
            alt={altitude.alt}
            missionStatus={runtime.missionStatus}
            activeFlightId={runtime.activeFlightId}
          />
        </>
      )}
    </Paper>
  );
}
