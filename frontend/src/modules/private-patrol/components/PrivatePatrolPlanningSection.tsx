import {
  Alert,
  Box,
  Stack,
  TextField,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import {
  TaskPreflightCommandsDrawer,
  useTaskPreflightCommandsDrawer,
} from "../../../modules/mission-workflow";
import {
  FieldBorderPanel,
  SavedFieldsPanel,
  type BorderMetrics,
  type FieldFeature,
  type LonLat,
} from "../../fields";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import {
  MissionCommandPanel,
  MissionPreflightPanel,
} from "../../mission-runtime";
import type { PreflightRunResponse } from "../../mission-runtime";
import type { PrivatePatrolMissionStatus } from "../types";
import type { usePrivatePatrolMission } from "../hooks/usePrivatePatrolMission";

type MissionVm = ReturnType<typeof usePrivatePatrolMission>;

export function PrivatePatrolFieldsBlock({
  fields,
  selectedFieldId,
  selectedField,
  loadingFields,
  deletingField,
  onSelectField,
  onRefreshFields,
  onFocusSelected,
  onDeleteSelected,
  fieldName,
  fieldBorder,
  metrics,
  savingField,
  onFieldNameChange,
  onSaveOrUpdate,
  onClearBorder,
  onNewField,
}: {
  fields: FieldFeature[];
  selectedFieldId: number | null;
  selectedField: FieldFeature | null;
  loadingFields: boolean;
  deletingField: boolean;
  onSelectField: (fieldId: number | null) => void;
  onRefreshFields: () => void;
  onFocusSelected: () => void;
  onDeleteSelected: () => void;
  fieldName: string;
  fieldBorder: LonLat[] | null;
  metrics: BorderMetrics | null;
  savingField: boolean;
  onFieldNameChange: (name: string) => void;
  onSaveOrUpdate: () => void;
  onClearBorder: () => void;
  onNewField: () => void;
}) {
  return (
    <Box
      sx={{
        mt: 1,
        display: "grid",
        gridTemplateColumns: {
          xs: "1fr",
          lg: "minmax(280px, 0.9fr) minmax(0, 1.6fr)",
        },
        gap: 2,
      }}
    >
      <SavedFieldsPanel
        fields={fields}
        selectedFieldId={selectedFieldId}
        selectedField={selectedField}
        loadingFields={loadingFields}
        deletingField={deletingField}
        onSelectField={onSelectField}
        onRefresh={onRefreshFields}
        onFocusSelected={onFocusSelected}
        onDeleteSelected={onDeleteSelected}
      />

      <Stack
        direction={{ xs: "column", lg: "row" }}
        spacing={1}
        alignItems={{ xs: "stretch", lg: "flex-start" }}
      >
        <FieldBorderPanel
          fieldName={fieldName}
          selectedFieldId={selectedFieldId}
          fieldBorder={fieldBorder}
          metrics={metrics}
          selectedFieldDisplayId={selectedField?.id ?? null}
          savingField={savingField}
          onFieldNameChange={onFieldNameChange}
          onSaveOrUpdate={onSaveOrUpdate}
          onClearBorder={onClearBorder}
          onNewField={onNewField}
        />
      </Stack>
    </Box>
  );
}

export function PrivatePatrolMissionControls({
  apiBase,
  preflightRun,
  telemetry,
  droneConnected,
  missionStatus,
  activeFlightId,
  mission,
  onSendMission,
}: {
  apiBase: string;
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  droneConnected: boolean;
  missionStatus: PrivatePatrolMissionStatus | null;
  activeFlightId: string | null;
  mission: MissionVm;
  onSendMission: () => void;
}) {
  const preflightCommandsDrawer = useTaskPreflightCommandsDrawer();

  const {
    name,
    setName,
    altInput,
    handleAltitudeInputChange,
    normalizeAltitude,
    sending,
    previewLoading,
    gridPreviewTooDense,
    gridPreviewError,
    hasRequiredTaskGeometry,
    isWaypointPatrol,
    isGridSurveillance,
    isEventTriggeredPatrol,
  } = mission;

  return (
    <>
      <Box
        sx={{
          width: { xs: "100%", md: 360 },
        }}
      >
        <Stack spacing={2}>
        <TextField
          variant="filled"
          label="Mission name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          size="small"
          fullWidth
          required
          error={!name.trim()}
          helperText={!name.trim() ? "Mission name is required" : " "}
        />

        <TextField
          variant="filled"
          label="Cruise altitude (m)"
          type="text"
          value={altInput}
          onChange={(e) => handleAltitudeInputChange(e.target.value)}
          onBlur={normalizeAltitude}
          size="small"
          fullWidth
          inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
          error={altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)}
          helperText={
            altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)
              ? "Must be between 1–500m"
              : " "
          }
        />

        <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1 }}>
          <ActionIconButton
            variant="play"
            title={
              sending
                ? isWaypointPatrol
                  ? "Starting Waypoint Patrol…"
                  : isGridSurveillance
                    ? "Starting Grid Surveillance…"
                    : isEventTriggeredPatrol
                      ? "Starting Event-Triggered Patrol…"
                      : "Starting Perimeter Patrol…"
                : isWaypointPatrol
                  ? "Start Waypoint Patrol"
                  : isGridSurveillance
                    ? "Start Grid Surveillance"
                    : isEventTriggeredPatrol
                      ? "Start Event-Triggered Patrol"
                      : "Start Perimeter Patrol"
            }
            color="success"
            size="medium"
            loading={sending}
            disabled={
              sending ||
              previewLoading ||
              (gridPreviewTooDense && !isWaypointPatrol) ||
              !!gridPreviewError ||
              !name.trim() ||
              altInput === "" ||
              Number(altInput) < 1 ||
              Number(altInput) > 500 ||
              !hasRequiredTaskGeometry
            }
            onClick={onSendMission}
          />
        </Stack>

        {activeFlightId && (
          <Alert severity="info" sx={{ mt: 2 }}>
            Active flight: {missionStatus?.mission_name || "Loading..."}
          </Alert>
        )}
      </Stack>
      </Box>

      <TaskPreflightCommandsDrawer
        open={preflightCommandsDrawer.open}
        onOpenChange={preflightCommandsDrawer.onOpenChange}
      >
        <MissionPreflightPanel
          apiBase={apiBase}
          missionType="perimeter_patrol"
          preflightRun={preflightRun}
          telemetry={telemetry}
        />
        <MissionCommandPanel
          telemetry={telemetry}
          droneConnected={droneConnected}
          missionStatus={missionStatus}
          activeFlightId={activeFlightId}
          apiBase={apiBase}
        />
      </TaskPreflightCommandsDrawer>
    </>
  );
}
