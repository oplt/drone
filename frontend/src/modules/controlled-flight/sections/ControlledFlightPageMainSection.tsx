import { Alert, Paper, Stack, Typography } from "@mui/material";
import { ErrorAlerts } from "../../../shared/ui/ErrorAlerts";
import { MissionStatusChips, MissionVideoPanel } from "../../mission-runtime";
import type { ControlledFlightPageSession } from "../hooks/useControlledFlightPageSession";
import { ControlledFlightControlsColumn } from "./ControlledFlightControlsColumn";
import { ControlledFlightMapColumn } from "./ControlledFlightMapColumn";

type ControlledFlightPageMainSectionProps = {
  session: ControlledFlightPageSession;
};

export function ControlledFlightPageMainSection({ session }: ControlledFlightPageMainSectionProps) {
  const {
    apiBase,
    apiKey,
    isLoaded,
    loadError,
    errors,
    addError,
    dismissError,
    clearErrors,
    runtime,
    commandMetrics,
    drawing,
    map,
    video,
    videoToken,
    userCenter,
    loadingLocation,
    droneCenter,
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
        <div>
          <Typography variant="h5">Controlled Flight Operations</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Connect to the drone, run preflight checks, and fly manually with keyboard or on-screen
            controls.
          </Typography>
        </div>
        <MissionStatusChips
          droneConnected={runtime.droneConnected}
          wsConnected={runtime.wsConnected}
        />
      </Stack>

      <ErrorAlerts errors={errors} onDismiss={dismissError} onClearAll={clearErrors} />

      {!apiKey ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          Missing Google Maps API Key. Set VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY in your .env file.
        </Alert>
      ) : loadError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to load Google Maps. {loadError.message}
        </Alert>
      ) : (
        <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ mb: 3 }}>
          <Stack sx={{ flex: 1, minHeight: 200 }} spacing={2}>
            <MissionVideoPanel
              title="Flight Camera"
              imgAlt="Pilot camera stream"
              disconnectedMessage="Connect the drone to view the live camera stream."
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
            <ControlledFlightMapColumn
              googleMap={map.googleMap}
              terraDrawRef={drawing.terraDrawRef}
              mapReady={map.mapReady}
              loadingLocation={loadingLocation}
              isLoaded={isLoaded}
              mapCenter={map.mapCenter}
              mapZoom={map.mapZoom}
              mapOptions={map.mapOptions}
              onMapClick={drawing.onMapClick}
              onMapLoad={map.onMapLoad}
              onMapUnmount={map.onMapUnmount}
              onMapZoomChanged={map.onMapZoomChanged}
              onMapCenterChanged={map.onMapCenterChanged}
              terraDrawMode={drawing.terraDrawMode}
              setTerraDrawReady={drawing.setTerraDrawReady}
              onMapError={addError}
              drawMode={drawing.drawMode}
              onDrawModeChange={drawing.setDrawMode}
              onToolModeChange={drawing.handleRouteToolModeChange}
              onUndo={drawing.undo}
              drawnPoints={drawing.drawnPoints}
              droneCenter={droneCenter}
              heading={heading}
              armed={commandMetrics.armed}
              userCenter={userCenter}
              activeFlightId={runtime.activeFlightId}
            />
          </Stack>
          <ControlledFlightControlsColumn session={session} />
        </Stack>
      )}
    </Paper>
  );
}
