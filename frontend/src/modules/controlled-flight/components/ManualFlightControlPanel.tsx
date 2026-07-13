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
  manualControlEnabled: boolean;
  manualControlReady: boolean;
  manualControlError: string | null;
  activeManualCommands: ManualFlightCommand[];
  lastManualCommand: LastManualCommand;
  onToggleKeyboard: () => void;
  onStopMovement: () => void;
  beginManualControl: (
    keyId: string,
    command: ManualFlightCommand,
    source: "keyboard" | "button",
  ) => void;
  endManualControl: (keyId: string, source: "keyboard" | "button") => void;
  controlledPreflight?: ControlledPreflightResult | null;
  preflightPassed?: boolean;
  preflightBusy?: boolean;
  onRunPreflight?: () => void;
};

export function ManualFlightControlPanel({
  controlledPreflight = null,
  preflightPassed,
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
  const usesWarehousePreflight = onRunPreflight == null;
  const passed = usesWarehousePreflight
    ? Boolean(preflightPassed)
    : Boolean(controlledPreflight?.passed);
  const statusLabel = usesWarehousePreflight
    ? passed
      ? "Ready"
      : "Blocked"
    : controlledPreflight == null
      ? "Not checked"
      : controlledPreflight.passed
        ? "Ready"
        : "Blocked";
  const statusColor: "default" | "success" | "error" =
    usesWarehousePreflight
      ? passed
        ? "success"
        : "error"
      : controlledPreflight == null
        ? "default"
        : controlledPreflight.passed
          ? "success"
          : "error";

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Keyboard Flight
          </Typography>
          <Chip size="small" color={statusColor} label={statusLabel} />
        </Stack>

        <Stack direction="row" spacing={0.25} flexWrap="wrap" useFlexGap>
          {onRunPreflight && (
            <ActionIconButton
              variant="preflight"
              title={preflightBusy ? "Checking…" : "Preflight"}
              color="success"
              loading={preflightBusy}
              onClick={onRunPreflight}
            />
          )}
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

        {!usesWarehousePreflight && controlledPreflight?.checks?.length ? (
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
        ) : null}

        {!usesWarehousePreflight && !controlledPreflight?.checks?.length ? (
          <Alert severity="info">Run preflight before enabling keyboard flight.</Alert>
        ) : null}

        {usesWarehousePreflight && !passed ? (
          <Alert severity="info">
            Complete Warehouse Preflight above before enabling keyboard flight.
          </Alert>
        ) : null}

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
            const isOneShot = button.command === "takeoff" || button.command === "land";
            return (
              <Tooltip key={button.id} title={button.hint} placement="top" arrow>
                <span>
                  <Button
                    size="small"
                    variant={isActive ? "contained" : "outlined"}
                    color={button.command === "hold" ? "warning" : "primary"}
                    disabled={!manualControlReady}
                    onClick={isOneShot ? () => void beginManualControl(button.id, button.command, "button") : undefined}
                    onMouseDown={isOneShot ? undefined : () => beginManualControl(button.id, button.command, "button")}
                    onMouseUp={isOneShot ? undefined : () => endManualControl(button.id, "button")}
                    onMouseLeave={isOneShot ? undefined : () => endManualControl(button.id, "button")}
                    onTouchStart={(event) => {
                      if (isOneShot) return;
                      event.preventDefault();
                      beginManualControl(button.id, button.command, "button");
                    }}
                    onTouchEnd={(event) => {
                      if (isOneShot) return;
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
