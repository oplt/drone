import { Box, Divider, Stack, Typography } from "@mui/material";
import FlightTakeoffRoundedIcon from "@mui/icons-material/FlightTakeoffRounded";
import {
  TaskPreflightCommandsDrawer,
  useTaskPreflightCommandsDrawer,
} from "../../../modules/mission-workflow";
import {
  type BorderMetrics,
  type FieldFeature,
  type LonLat,
} from "../../fields";
import { PropertyGeofencesPanel } from "./PropertyGeofencesPanel";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import {
  MissionCommandPanel,
  MissionPreflightPanel,
} from "../../mission-runtime";
import type { PreflightRunResponse } from "../../mission-runtime";
import type { PrivatePatrolMissionStatus } from "../types";
import type { PatrolSensorIntegration } from "../api/eventTriggerConfigApi";
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
                                           onSaveField,
                                           onUpdateField,
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
  onSaveField: () => void | Promise<void>;
  onUpdateField: () => void | Promise<void>;
  onNewField: () => void;
}) {
  return (
      <Box sx={{ mt: 1, minWidth: 0 }}>
        <PropertyGeofencesPanel
            fields={fields}
            selectedFieldId={selectedFieldId}
            selectedField={selectedField}
            loadingFields={loadingFields}
            deletingField={deletingField}
            fieldName={fieldName}
            fieldBorder={fieldBorder}
            metrics={metrics}
            savingField={savingField}
            onSelectField={onSelectField}
            onRefresh={onRefreshFields}
            onFocusSelected={onFocusSelected}
            onDeleteSelected={onDeleteSelected}
            onFieldNameChange={onFieldNameChange}
            onStartNew={onNewField}
            onSave={onSaveField}
            onUpdate={onUpdateField}
        />
      </Box>
  );
}

export function PrivatePatrolSetupPanel({
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
                                          onSaveField,
                                          onUpdateField,
                                          onNewField,
                                          mission,
                                          eventTriggerIntegration,
                                          eventTriggerSaving,
                                          eventTriggerSaveError,
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
  onSaveField: () => void | Promise<void>;
  onUpdateField: () => void | Promise<void>;
  onNewField: () => void;
  mission: MissionVm;
  eventTriggerIntegration: PatrolSensorIntegration | null;
  eventTriggerSaving?: boolean;
  eventTriggerSaveError?: string | null;
}) {
  return (
      <>
        <PrivatePatrolFieldsBlock
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
            onSaveField={onSaveField}
            onUpdateField={onUpdateField}
            onNewField={onNewField}
        />
        <PrivatePatrolParamsSection
            mission={mission}
            selectedFieldId={selectedFieldId}
            hasPropertyGeofence={Boolean(fieldBorder && fieldBorder.length >= 3)}
            eventTriggerIntegration={eventTriggerIntegration}
            eventTriggerSaving={eventTriggerSaving}
            eventTriggerSaveError={eventTriggerSaveError}
        />
        <Typography variant="body2" color="text.secondary">
          {mission.mapHint}
        </Typography>
      </>
  );
}

export function PrivatePatrolMissionControlsPanel({
                                                    apiBase,
                                                    mission,
                                                    preflightRun,
                                                    telemetry,
                                                    droneConnected,
                                                    missionStatus,
                                                    activeFlightId,
                                                  }: {
  apiBase: string;
  mission: MissionVm;
  preflightRun: PreflightRunResponse | null;
  telemetry: TelemetrySnapshot | null;
  droneConnected: boolean;
  missionStatus: PrivatePatrolMissionStatus | null;
  activeFlightId: string | null;
}) {
  const preflightBlockedReason = !mission.name.trim()
      ? "Enter a mission name above before running preflight."
      : mission.altInput === "" ||
      Number(mission.altInput) < 1 ||
      Number(mission.altInput) > 500
          ? "Set a valid cruise altitude above before running preflight."
          : !mission.hasRequiredTaskGeometry
              ? "Complete mission setup (geofence, waypoints, or event location) before running preflight."
              : mission.gridPreviewTooDense && !mission.isWaypointPatrol
                  ? "Patrol preview is too dense. Adjust route parameters first."
                  : mission.gridPreviewError
                      ? mission.gridPreviewError
                      : null;

  const preflightRunHint =
    preflightBlockedReason == null && !droneConnected
      ? "Drone is offline. Clicking Run will attempt to connect, then run checks."
      : undefined;

  return (
      <Stack spacing={1.5}>
        <MissionPreflightPanel
            apiBase={apiBase}
            missionType="perimeter_patrol"
            preflightRun={preflightRun}
            telemetry={telemetry}
            droneConnected={droneConnected}
            onRunPreflight={() => {
              void mission.runPreflightCheck();
            }}
            preflightBusy={mission.preflightBusy}
            runDisabled={
                mission.preflightBusy ||
                mission.sending ||
                preflightBlockedReason != null
            }
            runDisabledReason={preflightBlockedReason ?? undefined}
            runHint={preflightRunHint}
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

export function PrivatePatrolFlightDrawer({
                                            apiBase,
                                            mission,
                                            onSendMission,
                                            activeFlightId,
                                            missionStatus,
                                            telemetry,
                                            droneConnected,
                                          }: {
  apiBase: string;
  mission: MissionVm;
  onSendMission: () => void;
  activeFlightId: string | null;
  missionStatus: PrivatePatrolMissionStatus | null;
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
        <PrivatePatrolFlightSection
            embedded
            mission={mission}
            onSendMission={onSendMission}
            activeFlightId={activeFlightId}
            missionStatus={missionStatus}
        />
        <Divider />
        <PrivatePatrolMissionControlsPanel
            apiBase={apiBase}
            mission={mission}
            preflightRun={mission.preflightRun}
            telemetry={telemetry}
            droneConnected={droneConnected}
            missionStatus={missionStatus}
            activeFlightId={activeFlightId}
        />
      </TaskPreflightCommandsDrawer>
  );
}