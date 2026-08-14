import {
  Alert,
  Chip,
  FormControlLabel,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import type { PatrolSensorIntegration } from "../../api/eventTriggerConfigApi";
import { EventTriggerConnectionPanel } from "../EventTriggerConnectionPanel";
import { PatrolSpeedField } from "./PatrolSpeedField";
import { PARAM_FIELD_SX, PARAM_FULL_ROW_SX } from "./patrolParamsLayout";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

type PatrolEventTriggeredParamsFieldsProps = PatrolParamsFieldProps & {
  hasEventTriggerGeometry: boolean;
  eventTriggerIntegration: PatrolSensorIntegration | null;
  selectedFieldId: number | null;
  hasPropertyGeofence: boolean;
  eventTriggerSaving?: boolean;
  eventTriggerSaveError?: string | null;
  eventLocation: { lat: number; lon: number } | null;
};

export function PatrolEventTriggeredParamsFields({
  gridParams,
  setGridParams,
  activeTab,
  hasEventTriggerGeometry,
  eventTriggerIntegration,
  selectedFieldId,
  hasPropertyGeofence,
  eventTriggerSaving,
  eventTriggerSaveError,
  eventLocation,
}: PatrolEventTriggeredParamsFieldsProps) {
  return (
    <>
      <PatrolSpeedField
        gridParams={gridParams}
        setGridParams={setGridParams}
        activeTab={activeTab}
      />
      <TextField
        variant="filled"
        label="Verification loiter (s)"
        type="number"
        size="small"
        fullWidth
        sx={PARAM_FIELD_SX.s}
        value={gridParams.verification_loiter_s}
        onChange={(e) => {
          const value = Number(e.target.value);
          if (!Number.isFinite(value)) return;
          setGridParams((p) => ({
            ...p,
            verification_loiter_s: Math.min(600, Math.max(0, value)),
          }));
        }}
        inputProps={{ min: 0, max: 600, step: 1 }}
      />
      <TextField
        variant="filled"
        label="Verification radius (m)"
        type="number"
        size="small"
        fullWidth
        sx={PARAM_FIELD_SX.m}
        value={gridParams.verification_radius_m}
        onChange={(e) => {
          const value = Number(e.target.value);
          if (!Number.isFinite(value)) return;
          setGridParams((p) => ({
            ...p,
            verification_radius_m: Math.min(150, Math.max(0, value)),
          }));
        }}
        inputProps={{ min: 0, max: 150, step: 1 }}
      />
      <TextField
        variant="filled"
        label="Target label"
        size="small"
        fullWidth
        sx={PARAM_FIELD_SX.xs}
        value={gridParams.target_label}
        onChange={(e) =>
          setGridParams((p) => ({
            ...p,
            target_label: e.target.value,
          }))
        }
        placeholder="e.g. unknown vehicle"
      />
      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={gridParams.track_target}
            onChange={(e) =>
              setGridParams((p) => ({
                ...p,
                track_target: e.target.checked,
              }))
            }
          />
        }
        label={<Typography variant="body2">Track target</Typography>}
        sx={PARAM_FIELD_SX.xs}
      />
      {!hasEventTriggerGeometry && (
        <Alert severity="info" sx={{ py: 0.5, ...PARAM_FULL_ROW_SX }}>
          Set an event location on the map or use the saved property geofence for
          area search when coordinates are omitted.
        </Alert>
      )}
      <EventTriggerConnectionPanel
        integration={eventTriggerIntegration}
        selectedFieldId={selectedFieldId}
        hasGeofence={hasPropertyGeofence}
        saving={eventTriggerSaving}
        saveError={eventTriggerSaveError}
      />
      {eventLocation && (
        <Chip
          size="small"
          color="error"
          variant="outlined"
          sx={{ flexBasis: "100%", width: "fit-content" }}
          label={`Event at ${eventLocation.lat.toFixed(5)}, ${eventLocation.lon.toFixed(5)}`}
        />
      )}
    </>
  );
}
