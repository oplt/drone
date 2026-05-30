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
import type { MissionStatus } from "../../mission-workflow";
import type { PreflightRunResponse } from "../../mission-runtime";

export function FieldSurveyFieldsBlock({
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

export function FieldSurveyMissionControls({
  apiBase,
  fieldBorder,
  preflightRun,
  telemetry,
  droneConnected,
  missionStatus,
  activeFlightId,
  name,
  onNameChange,
  altInput,
  onAltInputChange,
  onAltBlur,
  sending,
  previewLoading,
  gridPreviewTooDense,
  gridPreviewError,
  onSendMission,
}: {
  apiBase: string;
  fieldBorder: LonLat[] | null;
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  droneConnected: boolean;
  missionStatus: MissionStatus | null;
  activeFlightId: string | null;
  name: string;
  onNameChange: (name: string) => void;
  altInput: string;
  onAltInputChange: (value: string) => void;
  onAltBlur: () => void;
  sending: boolean;
  previewLoading: boolean;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null | undefined;
  onSendMission: () => void;
}) {
  const preflightCommandsDrawer = useTaskPreflightCommandsDrawer();

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
            onChange={(e) => onNameChange(e.target.value)}
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
            onChange={(e) => onAltInputChange(e.target.value)}
            onBlur={onAltBlur}
            size="small"
            fullWidth
            inputProps={{ inputMode: "numeric", pattern: "\\d*" }}
            error={
              altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)
            }
            helperText={
              altInput !== "" && (Number(altInput) < 1 || Number(altInput) > 500)
                ? "Must be between 1–500m"
                : " "
            }
          />

          <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1 }}>
            <ActionIconButton
              variant="play"
              title={sending ? "Starting Grid Survey…" : "Start Grid Survey"}
              color="success"
              size="medium"
              loading={sending}
              disabled={
                sending ||
                previewLoading ||
                gridPreviewTooDense ||
                !!gridPreviewError ||
                !name.trim() ||
                altInput === "" ||
                Number(altInput) < 1 ||
                Number(altInput) > 500 ||
                !fieldBorder ||
                fieldBorder.length < 3
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
          missionType="grid"
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
