import { Divider, Stack, Typography } from "@mui/material";
import FlightTakeoffRoundedIcon from "@mui/icons-material/FlightTakeoffRounded";
import {
  TaskPreflightCommandsDrawer,
  useTaskPreflightCommandsDrawer,
} from "../../../modules/mission-workflow";
import { WorkflowFieldsBlock } from "../../fields/components/WorkflowFieldsBlock";
import type { BorderMetrics, FieldFeature, LonLat } from "../../fields";
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
    <WorkflowFieldsBlock
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
      compact={compact}
    />
  );
}

export function FieldSurveySetupPanel({
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
  return (
    <>
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
    </>
  );
}

export function FieldSurveyMissionControlsPanel({
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
  return (
    <Stack spacing={1.5}>
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
    </Stack>
  );
}

export function FieldSurveyFlightDrawer({
  apiBase,
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
  preflightRun,
  telemetry,
  droneConnected,
}: {
  apiBase: string;
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
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  droneConnected: boolean;
}) {
  const flightDrawer = useTaskPreflightCommandsDrawer();

  return (
    <TaskPreflightCommandsDrawer
      open={flightDrawer.open}
      onOpenChange={flightDrawer.onOpenChange}
      title="Flight"
      subtitle="Mission launch, preflight checks, and live commands"
      tabLabel="FLIGHT"
      tabIcon={<FlightTakeoffRoundedIcon fontSize="small" />}
      edgeTabCount={1}
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
      <Divider />
      <FieldSurveyMissionControlsPanel
        apiBase={apiBase}
        preflightRun={preflightRun}
        telemetry={telemetry}
        droneConnected={droneConnected}
        missionStatus={missionStatus}
        activeFlightId={activeFlightId}
      />
    </TaskPreflightCommandsDrawer>
  );
}
