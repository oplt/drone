import {
  Box,
  Stack,
  Typography,
} from "@mui/material";
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
import type { PreflightRunResponse } from "../../mission-runtime";
import type { PrivatePatrolMissionStatus } from "../types";
import type { usePrivatePatrolMission } from "../hooks/usePrivatePatrolMission";
import { PrivatePatrolFlightSection } from "./PrivatePatrolFlightSection";
import { PrivatePatrolParamsSection } from "./PrivatePatrolParamsSection";

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
        mt: 1,
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
        labels={{
          panelTitle: "Saved Property Geofences",
          panelInfo: "Select a saved property geofence to load and focus it on the map.",
          selectLabel: "Saved property geofences",
          refreshTitle: "Refresh property geofences",
          focusTitle: "Focus selected geofence",
          deleteTitle: "Delete selected geofence",
        }}
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
          labels={{
            panelTitle: "Property Geofence",
            panelInfo: "Draw a property geofence polygon on the map. Coordinates are stored as [lon, lat].",
            nameLabel: "Property name",
            saveTitle: "Save property geofence",
            updateTitle: "Update property geofence",
            newTitle: "New property geofence",
          }}
        />
      </Stack>
    </Box>
  );
}

export function PrivatePatrolSetupDrawer({
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
  mission,
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
  mission: MissionVm;
}) {
  const setupDrawer = useTaskPreflightCommandsDrawer();

  return (
    <TaskPreflightCommandsDrawer
      open={setupDrawer.open}
      onOpenChange={setupDrawer.onOpenChange}
      title="Set up"
      subtitle="Property geofence and patrol parameters"
      tabLabel="SET UP"
      tabIcon={<TuneRoundedIcon fontSize="small" />}
      edgeTabIndex={0}
      edgeTabCount={3}
      paperSx={{ width: { xs: "min(100vw, 440px)", sm: 480, md: 540 } }}
    >
      <PrivatePatrolFieldsBlock
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
      <PrivatePatrolParamsSection mission={mission} />
      <Typography variant="body2" color="text.secondary">
        {mission.mapHint}
      </Typography>
    </TaskPreflightCommandsDrawer>
  );
}

export function PrivatePatrolFlightDrawer({
  mission,
  onSendMission,
  activeFlightId,
  missionStatus,
}: {
  mission: MissionVm;
  onSendMission: () => void;
  activeFlightId: string | null;
  missionStatus: PrivatePatrolMissionStatus | null;
}) {
  const flightDrawer = useTaskPreflightCommandsDrawer();

  return (
    <TaskPreflightCommandsDrawer
      open={flightDrawer.open}
      onOpenChange={flightDrawer.onOpenChange}
      title="Flight"
      subtitle="Mission name, cruise altitude, and patrol start"
      tabLabel="FLIGHT"
      tabIcon={<FlightTakeoffRoundedIcon fontSize="small" />}
      edgeTabIndex={1}
      edgeTabCount={3}
      paperSx={{ width: { xs: "min(100vw, 420px)", sm: 440, md: 460 } }}
    >
      <PrivatePatrolFlightSection
        embedded
        mission={mission}
        onSendMission={onSendMission}
        activeFlightId={activeFlightId}
        missionStatus={missionStatus}
      />
    </TaskPreflightCommandsDrawer>
  );
}

export function PrivatePatrolMissionControls({
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
  missionStatus: PrivatePatrolMissionStatus | null;
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
  );
}
