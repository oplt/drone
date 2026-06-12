import { Box, Stack, Typography } from "@mui/material";
import FlightTakeoffRoundedIcon from "@mui/icons-material/FlightTakeoffRounded";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";
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
import { FieldSurveyFlightSection } from "./FieldSurveyFlightSection";
import { FieldSurveyGridParamsSection } from "./FieldSurveyGridParamsSection";
import type { GridParams } from "../../mission-planning";

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
  compact = false,
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
  compact?: boolean;
}) {
  return (
    <Box
      sx={{
        mt: compact ? 0 : 1,
        display: compact ? "flex" : "grid",
        flexDirection: compact ? "column" : undefined,
        gridTemplateColumns: compact
          ? undefined
          : {
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
        direction={compact ? "column" : { xs: "column", lg: "row" }}
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

export function FieldSurveySetupDrawer({
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
  gridParams,
  setGridParams,
  gridPreview,
  gridPreviewStats,
  previewLegStats,
  gridPreviewTooDense,
  gridPreviewError,
  previewLoading,
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
  gridParams: GridParams;
  setGridParams: React.Dispatch<React.SetStateAction<GridParams>>;
  gridPreview: { lat: number; lon: number }[] | null | undefined;
  gridPreviewStats: { route_m?: number; rows?: number } | null | undefined;
  previewLegStats: { workLegs: number; transitLegs: number } | null;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null | undefined;
  previewLoading: boolean;
}) {
  const setupDrawer = useTaskPreflightCommandsDrawer();

  return (
    <TaskPreflightCommandsDrawer
      open={setupDrawer.open}
      onOpenChange={setupDrawer.onOpenChange}
      title="Set up"
      subtitle="Field boundary, grid parameters, and route preview"
      tabLabel="SET UP"
      tabIcon={<TuneRoundedIcon fontSize="small" />}
      edgeTabIndex={0}
      edgeTabCount={3}
      paperSx={{ width: { xs: "min(100vw, 440px)", sm: 480, md: 540 } }}
    >
      <FieldSurveyFieldsBlock
        compact
        fields={fields}
        selectedFieldId={selectedFieldId}
        selectedField={selectedField}
        loadingFields={loadingFields}
        deletingField={deletingField}
        onSelectField={onSelectField}
        onRefreshFields={onRefreshFields}
        onFocusSelected={onFocusSelected}
        onDeleteSelected={onDeleteSelected}
        fieldName={fieldName}
        fieldBorder={fieldBorder}
        metrics={metrics}
        savingField={savingField}
        onFieldNameChange={onFieldNameChange}
        onSaveOrUpdate={onSaveOrUpdate}
        onClearBorder={onClearBorder}
        onNewField={onNewField}
      />
      <FieldSurveyGridParamsSection
        gridParams={gridParams}
        setGridParams={setGridParams}
        fieldBorder={fieldBorder}
        gridPreview={gridPreview}
        gridPreviewStats={gridPreviewStats}
        previewLegStats={previewLegStats}
        gridPreviewTooDense={gridPreviewTooDense}
        gridPreviewError={gridPreviewError}
        previewLoading={previewLoading}
      />
      <Typography variant="body2" color="text.secondary">
        Click on the map to add waypoints.
      </Typography>
    </TaskPreflightCommandsDrawer>
  );
}

export function FieldSurveyFlightDrawer({
  fieldBorder,
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
  activeFlightId,
  missionStatus,
}: {
  fieldBorder: LonLat[] | null;
  name: string;
  onNameChange: (value: string) => void;
  altInput: string;
  onAltInputChange: (value: string) => void;
  onAltBlur: () => void;
  sending: boolean;
  previewLoading: boolean;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null | undefined;
  onSendMission: () => void;
  activeFlightId: string | null;
  missionStatus: MissionStatus | null;
}) {
  const flightDrawer = useTaskPreflightCommandsDrawer();

  return (
    <TaskPreflightCommandsDrawer
      open={flightDrawer.open}
      onOpenChange={flightDrawer.onOpenChange}
      title="Flight"
      subtitle="Mission name, cruise altitude, and survey start"
      tabLabel="FLIGHT"
      tabIcon={<FlightTakeoffRoundedIcon fontSize="small" />}
      edgeTabIndex={1}
      edgeTabCount={3}
      paperSx={{ width: { xs: "min(100vw, 420px)", sm: 440, md: 460 } }}
    >
      <FieldSurveyFlightSection
        embedded
        name={name}
        onNameChange={onNameChange}
        altInput={altInput}
        onAltInputChange={onAltInputChange}
        onAltBlur={onAltBlur}
        sending={sending}
        previewLoading={previewLoading}
        gridPreviewTooDense={gridPreviewTooDense}
        gridPreviewError={gridPreviewError}
        fieldBorder={fieldBorder}
        onSendMission={onSendMission}
        activeFlightId={activeFlightId}
        missionStatus={missionStatus}
      />
    </TaskPreflightCommandsDrawer>
  );
}

export function FieldSurveyMissionControls({
  apiBase,
  preflightRun,
  telemetry,
  droneConnected,
  missionStatus,
  activeFlightId,
}: {
  apiBase: string;
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  droneConnected: boolean;
  missionStatus: MissionStatus | null;
  activeFlightId: string | null;
}) {
  const preflightCommandsDrawer = useTaskPreflightCommandsDrawer();

  return (
    <TaskPreflightCommandsDrawer
      open={preflightCommandsDrawer.open}
      onOpenChange={preflightCommandsDrawer.onOpenChange}
      edgeTabIndex={2}
      edgeTabCount={3}
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
  );
}
