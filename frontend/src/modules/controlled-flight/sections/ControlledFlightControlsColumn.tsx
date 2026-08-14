import {
  Alert,
  Box,
  Chip,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { ManualFlightControlPanel } from "../components/ManualFlightControlPanel";
import type { ControlledFlightPageSession } from "../hooks/useControlledFlightPageSession";

type ControlledFlightControlsColumnProps = {
  session: ControlledFlightPageSession;
};

export function ControlledFlightControlsColumn({ session }: ControlledFlightControlsColumnProps) {
  const { altitude, runtime, missionLauncher, droneSession } = session;
  const { manualControls } = droneSession;

  return (
    <Box sx={{ width: { xs: "100%", md: 360 } }}>
      <Stack spacing={0.5}>
        <Paper variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
          <Stack spacing={0.5}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              Drone control
            </Typography>
            <Stack direction="row" spacing={0.25} flexWrap="wrap" useFlexGap>
              <ActionIconButton
                variant="connect"
                title={
                  droneSession.connecting
                    ? "Connecting…"
                    : droneSession.droneManualConnected
                      ? "Drone connected"
                      : "Connect drone"
                }
                color={droneSession.droneManualConnected ? "success" : "primary"}
                loading={droneSession.connecting}
                disabled={droneSession.connecting || droneSession.droneManualConnected}
                onClick={() => void droneSession.connectDrone()}
              />
            </Stack>
            <Chip
              size="small"
              color={
                droneSession.controlledPreflight == null
                  ? "default"
                  : droneSession.controlledPreflight.passed
                    ? "success"
                    : "error"
              }
              label={
                droneSession.controlledPreflight == null
                  ? "Not checked"
                  : droneSession.controlledPreflight.passed
                    ? "GREEN — Ready"
                    : "BLOCKED"
              }
            />
          </Stack>
        </Paper>

        <ManualFlightControlPanel
          controlledPreflight={droneSession.controlledPreflight}
          manualControlEnabled={droneSession.manualControlEnabled}
          manualControlReady={droneSession.manualControlReady}
          manualControlError={manualControls.manualControlError}
          activeManualCommands={manualControls.activeManualCommands}
          lastManualCommand={manualControls.lastManualCommand}
          preflightBusy={droneSession.connecting}
          onRunPreflight={() => void droneSession.runManualPreflightCheck()}
          onToggleKeyboard={() => {
            if (droneSession.manualControlEnabled) {
              droneSession.setManualControlEnabled(false);
              manualControls.stopAllManualCommands();
              return;
            }
            droneSession.setManualControlEnabled(true);
            manualControls.setManualControlError(null);
          }}
          onStopMovement={() => manualControls.stopAllManualCommands("button")}
          beginManualControl={manualControls.beginManualControl}
          endManualControl={manualControls.endManualControl}
        />

        <TextField
          variant="filled"
          label="Session name"
          value={missionLauncher.name}
          onChange={(event) => missionLauncher.setName(event.target.value)}
          size="small"
          fullWidth
          required
          error={!missionLauncher.name.trim()}
          helperText={!missionLauncher.name.trim() ? "Session name is required" : " "}
        />

        <TextField
          variant="filled"
          label="Cruise altitude (m)"
          type="text"
          value={altitude.altInput}
          onChange={(event) => altitude.handleAltitudeInputChange(event.target.value)}
          onBlur={altitude.normalizeAltitude}
          size="small"
          fullWidth
          inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
          error={
            altitude.altInput !== "" &&
            (Number(altitude.altInput) < 1 || Number(altitude.altInput) > 500)
          }
          helperText={
            altitude.altInput !== "" &&
            (Number(altitude.altInput) < 1 || Number(altitude.altInput) > 500)
              ? "Must be between 1–500m"
              : " "
          }
        />

        <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1 }}>
          <ActionIconButton
            variant="play"
            title={missionLauncher.sending ? "Starting session…" : "Start Controlled Flight Session"}
            color="success"
            size="medium"
            loading={missionLauncher.sending}
            disabled={
              missionLauncher.sending ||
              !missionLauncher.name.trim() ||
              altitude.altInput === "" ||
              Number(altitude.altInput) < 1 ||
              Number(altitude.altInput) > 500
            }
            onClick={() => void missionLauncher.sendMission()}
          />
        </Stack>

        {runtime.activeFlightId && (
          <Alert severity="info" sx={{ mt: 1 }}>
            Active flight: {runtime.missionStatus?.mission_name || runtime.activeFlightId}
          </Alert>
        )}

        {runtime.missionStatus && runtime.activeFlightId && (
          <Box sx={{ p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: "bold", mb: 1 }}>
              Flight Status
            </Typography>
            <Stack spacing={0.5}>
              {runtime.missionStatus.flight_id && (
                <Typography variant="caption" component="div">
                  Flight ID: {runtime.missionStatus.flight_id}
                </Typography>
              )}
              <Typography variant="caption" component="div">
                Telemetry:{" "}
                {runtime.missionStatus.telemetry?.running ? (
                  <span style={{ color: "green" }}>Running</span>
                ) : (
                  <span style={{ color: "red" }}>Stopped</span>
                )}
              </Typography>
              {runtime.missionStatus.telemetry?.active_connections !== undefined && (
                <Typography variant="caption" component="div">
                  WS Connections: {runtime.missionStatus.telemetry.active_connections}
                </Typography>
              )}
              <Typography variant="caption" component="div">
                Drone Connected:{" "}
                {runtime.missionStatus.orchestrator?.drone_connected ? (
                  <span style={{ color: "green" }}>Yes</span>
                ) : (
                  <span style={{ color: "red" }}>No</span>
                )}
              </Typography>
              {droneSession.batteryPercent != null && (
                <Typography variant="caption" component="div">
                  Battery: {droneSession.batteryPercent.toFixed(0)}%
                </Typography>
              )}
              {droneSession.gpsFixType != null && (
                <Typography variant="caption" component="div">
                  GPS Fix: {droneSession.gpsFixType}
                </Typography>
              )}
            </Stack>
          </Box>
        )}
      </Stack>
    </Box>
  );
}
