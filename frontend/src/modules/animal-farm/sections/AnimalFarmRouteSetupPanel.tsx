import { Alert, Stack, TextField, Typography } from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";

type AnimalFarmRouteSetupPanelProps = {
  name: string;
  onNameChange: (value: string) => void;
  altInput: string;
  onAltitudeInputChange: (value: string) => void;
  onAltitudeBlur: () => void;
  waypointCount: number;
  sending: boolean;
  activeFlightId: string | null;
  activeMissionName?: string;
  onUndo: () => void;
  onClear: () => void;
  onSendMission: () => void;
};

export function AnimalFarmRouteSetupPanel({
  name,
  onNameChange,
  altInput,
  onAltitudeInputChange,
  onAltitudeBlur,
  waypointCount,
  sending,
  activeFlightId,
  activeMissionName,
  onUndo,
  onClear,
  onSendMission,
}: AnimalFarmRouteSetupPanelProps) {
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Click on the map to add waypoints. Markers are ordered (1..N).
      </Typography>
      <TextField
        variant="filled"
        label="Field plan name"
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        size="small"
        fullWidth
        required
        error={!name.trim()}
        helperText={!name.trim() ? "Field plan name is required" : ""}
      />
      <TextField
        variant="filled"
        label="Cruise altitude (m)"
        type="text"
        value={altInput}
        onChange={(e) => onAltitudeInputChange(e.target.value)}
        onBlur={onAltitudeBlur}
        size="small"
        fullWidth
        inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
        error={altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)}
        helperText={
          altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)
            ? "Must be between 1–500m"
            : ""
        }
      />
      <Typography variant="subtitle2">Waypoints: {waypointCount}</Typography>
      <Stack direction="row" spacing={0.25}>
        <ActionIconButton
          variant="undo"
          title="Undo Last"
          disabled={waypointCount === 0 || sending}
          onClick={onUndo}
        />
        <ActionIconButton
          variant="delete"
          title="Clear All"
          color="error"
          disabled={waypointCount === 0 || sending}
          onClick={onClear}
        />
      </Stack>
      <Stack direction="row" justifyContent="flex-end">
        <ActionIconButton
          variant="play"
          title={sending ? "Sending…" : "Start Flight Plan"}
          color="primary"
          size="medium"
          loading={sending}
          disabled={
            sending ||
            waypointCount < 2 ||
            !name.trim() ||
            altInput === "" ||
            Number(altInput) < 1 ||
            Number(altInput) > 500
          }
          onClick={onSendMission}
        />
      </Stack>
      {activeFlightId && (
        <Alert severity="info">
          Active flight: {activeMissionName || "Loading..."}
        </Alert>
      )}
    </Stack>
  );
}
