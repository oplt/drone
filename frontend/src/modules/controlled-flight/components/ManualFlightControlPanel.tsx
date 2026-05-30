import { Alert, Box, Button, Chip, Paper, Stack, Tooltip, Typography } from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { ControlledPreflightResult, ManualFlightCommand } from "../types";
import { MANUAL_CONTROL_BUTTONS } from "../types";

type LastManualCommand = {
  command: ManualFlightCommand;
  phase: string;
  source: "keyboard" | "button";
  sentAt: string;
} | null;

type Props = {
  controlledPreflight: ControlledPreflightResult | null;
  manualControlEnabled: boolean;
  manualControlReady: boolean;
  manualControlError: string | null;
  preflightBusy?: boolean;
  activeManualCommands: ManualFlightCommand[];
  lastManualCommand: LastManualCommand;
  onRunPreflight: () => void;
  onToggleKeyboard: () => void;
  onStopMovement: () => void;
  beginManualControl: (
    keyId: string,
    command: ManualFlightCommand,
    source: "keyboard" | "button",
  ) => void;
  endManualControl: (keyId: string, source: "keyboard" | "button") => void;
};

export function ManualFlightControlPanel({
  controlledPreflight,
  manualControlEnabled,
  manualControlReady,
  manualControlError,
  preflightBusy = false,
  activeManualCommands,
  lastManualCommand,
  onRunPreflight,
  onToggleKeyboard,
  onStopMovement,
  beginManualControl,
  endManualControl,
}: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Keyboard Flight
          </Typography>
          <Chip
            size="small"
            color={
              controlledPreflight == null
                ? "default"
                : controlledPreflight.passed
                  ? "success"
                  : "error"
            }
            label={
              controlledPreflight == null
                ? "Not checked"
                : controlledPreflight.passed
                  ? "Ready"
                  : "Blocked"
            }
          />
        </Stack>

        <Stack direction="row" spacing={0.25} flexWrap="wrap" useFlexGap>
          <ActionIconButton
            variant="preflight"
            title={preflightBusy ? "Checking…" : "Preflight"}
            color="success"
            loading={preflightBusy}
            onClick={onRunPreflight}
          />
          <ActionIconButton
            variant="keyboard"
            title={manualControlEnabled ? "Disable keys" : "Enable keys"}
            color={manualControlEnabled ? "warning" : "primary"}
            disabled={!manualControlReady && !manualControlEnabled}
            onClick={onToggleKeyboard}
          />
          <ActionIconButton
            variant="stop"
            title="Stop"
            color="error"
            disabled={activeManualCommands.length === 0}
            onClick={onStopMovement}
          />
        </Stack>

        {controlledPreflight?.checks?.length ? (
          <Stack spacing={1}>
            {controlledPreflight.checks.map((check) => (
              <Paper
                key={check.id}
                variant="outlined"
                sx={{
                  px: 1.25,
                  py: 1,
                  borderRadius: 1.5,
                  borderColor: check.ok ? "success.light" : "error.light",
                }}
              >
                <Stack direction="row" spacing={1} justifyContent="space-between">
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {check.label}
                  </Typography>
                  <Chip size="small" color={check.ok ? "success" : "error"} label={check.ok ? "Green" : "Blocked"} />
                </Stack>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  {check.detail}
                </Typography>
              </Paper>
            ))}
          </Stack>
        ) : (
          <Alert severity="info">Run preflight before enabling keyboard flight.</Alert>
        )}

        {manualControlEnabled ? (
          <Alert severity="success">
            Keyboard active: W/A/S/D or arrows move, Q/E yaw, R/F altitude, Space hold, T takeoff, L land.
          </Alert>
        ) : (
          <Alert severity={manualControlReady ? "warning" : "info"}>
            {manualControlReady
              ? "Preflight is green. Enable keyboard control to fly."
              : "Keyboard control is locked until preflight passes."}
          </Alert>
        )}

        {manualControlError && <Alert severity="error">{manualControlError}</Alert>}

        <Box
          sx={{
            display: "flex",
            flexDirection: "row",
            flexWrap: "nowrap",
            gap: 0.5,
            minWidth: 0,
            overflowX: "auto",
            pb: 0.25,
          }}
        >
          {MANUAL_CONTROL_BUTTONS.map((button) => {
            const isActive = activeManualCommands.includes(button.command);
            return (
              <Tooltip key={button.id} title={button.hint} placement="top" arrow>
                <span>
                  <Button
                    size="small"
                    variant={isActive ? "contained" : "outlined"}
                    color={button.command === "hold" ? "warning" : "primary"}
                    disabled={!manualControlReady}
                    onMouseDown={() => beginManualControl(button.id, button.command, "button")}
                    onMouseUp={() => endManualControl(button.id, "button")}
                    onMouseLeave={() => endManualControl(button.id, "button")}
                    onTouchStart={(event) => {
                      event.preventDefault();
                      beginManualControl(button.id, button.command, "button");
                    }}
                    onTouchEnd={(event) => {
                      event.preventDefault();
                      endManualControl(button.id, "button");
                    }}
                    sx={{
                      flex: "1 0 auto",
                      minWidth: 0,
                      minHeight: 32,
                      px: 0.75,
                      py: 0.35,
                      fontSize: "0.68rem",
                      lineHeight: 1.1,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {button.label}
                  </Button>
                </span>
              </Tooltip>
            );
          })}
        </Box>

        {lastManualCommand && (
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            Last: {lastManualCommand.command} ({lastManualCommand.phase}) via{" "}
            {lastManualCommand.source} at {new Date(lastManualCommand.sentAt).toLocaleTimeString()}.
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}
