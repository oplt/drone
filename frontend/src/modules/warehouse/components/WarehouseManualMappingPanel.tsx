import { Alert, Chip, Paper, Stack, Typography } from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
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
  wsConnected: boolean;
  droneConnected: boolean;
  warehouseMapId: number | null;
  sensorRigId: number | null;
  dockId: number | null;
  warehousePreflightPassed: boolean;
  setPendingFlightId: (flightId: string | null) => void;
  onPreflightRun: (preflight: PreflightRunResponse | null) => void;
  onMessage: (message: string) => void;
  onError: (message: string) => void;
  onScanResultReady?: (jobId: number) => void;
  embedded?: boolean;
};

export function WarehouseManualMappingPanel({ embedded = false, ...props }: Props) {
  const manualMapping = useWarehouseManualMapping(props);
  const { manual } = manualMapping;

  const stackLabel = (() => {
    if (manualMapping.mappingBusy) return "Mapping stack: updating…";
    if (manualMapping.mappingActiveFlightId) {
      return manualMapping.mappingStackStatus?.running
        ? `Mapping stack: running (pid ${manualMapping.mappingStackStatus.pid ?? "?"})`
        : "Mapping stack: session active, stack stopped";
    }
    if (manualMapping.mappingStackStatus?.running) {
      return `Mapping stack: running (pid ${manualMapping.mappingStackStatus.pid ?? "?"})`;
    }
    if (manualMapping.mappingStackStatus?.last_error) {
      return `Mapping stack: failed (${manualMapping.mappingStackStatus.last_error})`;
    }
    return "Mapping stack: stopped";
  })();

  const stackColor: "default" | "success" | "warning" | "error" =
    manualMapping.mappingBusy
      ? "warning"
      : manualMapping.mappingStackStatus?.last_error
        ? "error"
        : manualMapping.mappingStackStatus?.running ||
            manualMapping.mappingActiveFlightId
          ? "success"
          : "default";

  const content = (
    <Stack spacing={1.25}>
      {!embedded && (
        <Typography variant="subtitle1">
          <InfoLabel
            label="Manual Warehouse Mapping"
            info="Start a controlled keyboard flight, start ROS mapping, fly the inbound area manually, then stop mapping after landing."
          />
        </Typography>
      )}
        <Chip size="small" label={stackLabel} color={stackColor} variant="outlined" />
        <Stack direction="row" spacing={0.25} flexWrap="wrap" useFlexGap>
          <ActionIconButton
            variant="connect"
            title={manualMapping.connecting ? "Connecting…" : "Connect Drone"}
            color="primary"
            loading={manualMapping.connecting}
            onClick={manualMapping.connectDrone}
          />
          <ActionIconButton
            variant="takeoff"
            title={manualMapping.startingSession ? "Starting…" : "Start Keyboard Flight"}
            color="primary"
            loading={manualMapping.startingSession}
            disabled={!props.warehousePreflightPassed}
            onClick={manualMapping.startKeyboardSession}
          />
          <ActionIconButton
            variant="play"
            title="Start ROS Mapping"
            color="success"
            disabled={manualMapping.mappingBusy || !props.activeFlightId || props.warehouseMapId == null}
            onClick={manualMapping.startMapping}
          />
          <ActionIconButton
            variant="stop"
            title="Stop ROS Mapping"
            color="warning"
            disabled={manualMapping.mappingBusy || !manualMapping.mappingActiveFlightId}
            onClick={manualMapping.stopMapping}
          />
        </Stack>
        {!props.warehousePreflightPassed && (
          <Alert severity="warning">
            Run Warehouse Preflight above before connecting or starting keyboard flight.
          </Alert>
        )}
        {!props.activeFlightId && props.warehousePreflightPassed && (
          <Alert severity="info">Start a keyboard flight session before enabling movement.</Alert>
        )}
        {manualMapping.mappingActiveFlightId && (
          <Alert severity="success">ROS mapping is recording for this keyboard flight.</Alert>
        )}
        <ManualFlightControlPanel
          preflightPassed={props.warehousePreflightPassed}
          manualControlEnabled={manualMapping.manualControlEnabled}
          manualControlReady={manualMapping.manualControlReady}
          manualControlError={manual.manualControlError}
          activeManualCommands={manual.activeManualCommands}
          lastManualCommand={manual.lastManualCommand}
          onToggleKeyboard={() => {
            if (manualMapping.manualControlEnabled) {
              manualMapping.setManualControlEnabled(false);
              manual.stopAllManualCommands();
              return;
            }
            manualMapping.setManualControlEnabled(true);
            manual.setManualControlError(null);
          }}
          onStopMovement={() => manual.stopAllManualCommands("button")}
          beginManualControl={manual.beginManualControl}
          endManualControl={manual.endManualControl}
        />
      </Stack>
  );

  if (embedded) return content;

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: "divider" }}>
      {content}
    </Paper>
  );
}
