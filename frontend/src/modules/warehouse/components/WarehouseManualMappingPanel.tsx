import { Alert, Button, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import type { PreflightRunResponse } from "../../mission-runtime";
import { ManualFlightControlPanel } from "../../controlled-flight/components/ManualFlightControlPanel";
import { useWarehouseManualMapping } from "../hooks/useWarehouseManualMapping";

type MissionStatusLike = {
  orchestrator?: { drone_connected?: boolean };
  telemetry?: { running?: boolean; has_position_data?: boolean };
};

type Props = {
  activeFlightId: string | null;
  missionStatus: MissionStatusLike | null;
  telemetry: unknown;
  wsConnected: boolean;
  droneConnected: boolean;
  warehouseMapId: number | null;
  sensorRigId: number | null;
  dockId: number | null;
  setPendingFlightId: (flightId: string | null) => void;
  onPreflightRun: (preflight: PreflightRunResponse | null) => void;
  onMessage: (message: string) => void;
  onError: (message: string) => void;
  onScanResultReady?: (jobId: number) => void;
};

export function WarehouseManualMappingPanel(props: Props) {
  const manualMapping = useWarehouseManualMapping(props);
  const { preflight, manual } = manualMapping;

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: "divider" }}>
      <Stack spacing={1.25}>
        <Typography variant="subtitle1">
          <InfoLabel
            label="Manual Warehouse Mapping"
            info="Start a controlled keyboard flight, start ROS mapping, fly the inbound area manually, then stop mapping after landing."
          />
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            variant="contained"
            disabled={manualMapping.connecting}
            onClick={manualMapping.connectDrone}
          >
            {manualMapping.connecting ? <CircularProgress size={16} /> : "Connect Drone"}
          </Button>
          <Button
            variant="contained"
            disabled={manualMapping.startingSession}
            onClick={manualMapping.startKeyboardSession}
          >
            {manualMapping.startingSession ? "Starting..." : "Start Keyboard Flight"}
          </Button>
          <Button
            variant="outlined"
            color="success"
            disabled={manualMapping.mappingBusy || !props.activeFlightId || props.warehouseMapId == null}
            onClick={manualMapping.startMapping}
          >
            Start ROS Mapping
          </Button>
          <Button
            variant="outlined"
            color="warning"
            disabled={manualMapping.mappingBusy || !manualMapping.mappingActiveFlightId}
            onClick={manualMapping.stopMapping}
          >
            Stop ROS Mapping
          </Button>
        </Stack>
        {!props.activeFlightId && (
          <Alert severity="info">Start a keyboard flight session before enabling movement.</Alert>
        )}
        {manualMapping.mappingActiveFlightId && (
          <Alert severity="success">ROS mapping is recording for this keyboard flight.</Alert>
        )}
        <ManualFlightControlPanel
          controlledPreflight={preflight.controlledPreflight}
          manualControlEnabled={preflight.manualControlEnabled}
          manualControlReady={manualMapping.manualControlReady}
          manualControlError={manual.manualControlError}
          preflightBusy={manualMapping.preflightPreparing}
          activeManualCommands={manual.activeManualCommands}
          lastManualCommand={manual.lastManualCommand}
          onRunPreflight={() => {
            void manualMapping.runPreflightCheck();
          }}
          onToggleKeyboard={() => {
            if (preflight.manualControlEnabled) {
              preflight.setManualControlEnabled(false);
              manual.stopAllManualCommands();
              return;
            }
            preflight.setManualControlEnabled(true);
            manual.setManualControlError(null);
          }}
          onStopMovement={() => manual.stopAllManualCommands("button")}
          beginManualControl={manual.beginManualControl}
          endManualControl={manual.endManualControl}
        />
      </Stack>
    </Paper>
  );
}
