import { Divider, Stack } from "@mui/material";
import { TerraDrawController } from "../../maps";
import {
  GoogleMapEngineAlerts,
  MissionWorkflowShell,
} from "../../mission-workflow";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import { FieldDeleteDialog } from "../../field-survey/components/FieldDeleteDialog";
import { PrivatePatrolMapColumn } from "../components/PrivatePatrolMapColumn";
import {
  PrivatePatrolFlightDrawer,
  PrivatePatrolSetupPanel,
} from "../components/PrivatePatrolPlanningSection";
import { PrivatePatrolStatusSections } from "../components/PrivatePatrolStatusSections";
import { PrivatePatrolUiNotice } from "../components/PrivatePatrolUiNotice";
import { usePrivatePatrolPage } from "../hooks/usePrivatePatrolPage";

export default function PrivatePatrolPage() {
  const vm = usePrivatePatrolPage();
  const { map, mission, borderEditor } = vm;
  const telemetry = vm.telemetry as TelemetrySnapshot | null;

  return (
    <MissionWorkflowShell
      title="Property Patrol Mission"
      subtitle="Persistent surveillance missions for property security with perimeter patrol, key-point verification, grid area coverage, and event-triggered response workflows."
      droneConnected={vm.droneConnected}
      wsConnected={vm.wsConnected}
      errors={vm.errors}
      onDismissError={vm.dismissError}
      onClearErrors={vm.clearErrors}
    >
      <GoogleMapEngineAlerts
        mapEngine={map.mapEngine}
        apiKey={map.apiKey}
        loadError={map.loadError}
        mapId={map.mapId}
      />

      {vm.googleMapsReady ? (
        <>
          <TerraDrawController
            map={map.mapReady ? map.mapRef.current : null}
            enabled={map.mapEngine === "google"}
            mode={vm.terraDrawMode}
            drawRef={map.terraDrawRef}
            onReadyChange={map.setTerraDrawReady}
            onSnapshotChange={borderEditor.syncFieldBorderFromSnapshot}
            onError={vm.addError}
          />
          <Stack spacing={2} sx={{ mb: 3 }}>
            <PrivatePatrolMapColumn
              vm={vm}
              onSelectField={vm.selectField}
              setupContent={
                <PrivatePatrolSetupPanel
                  fields={vm.fields}
                  selectedFieldId={vm.selectedFieldId}
                  selectedField={vm.selectedField}
                  loadingFields={vm.loadingFields}
                  deletingField={vm.deletingField}
                  onSelectField={vm.handleSavedFieldSelect}
                  onRefreshFields={vm.refreshFields}
                  onFocusSelected={vm.focusSelectedField}
                  onDeleteSelected={vm.requestDeleteSelectedField}
                  fieldName={vm.fieldName}
                  fieldBorder={vm.fieldBorder}
                  metrics={vm.metrics}
                  savingField={vm.savingField}
                  onFieldNameChange={vm.setFieldName}
                  onSaveField={() => void vm.saveFieldBorder()}
                  onUpdateField={() => void vm.updateFieldBorder()}
                  onNewField={vm.handleNewField}
                  mission={mission}
                  eventTriggerIntegration={vm.eventTriggerIntegration}
                  eventTriggerSaving={vm.eventTriggerSaving}
                  eventTriggerSaveError={vm.eventTriggerSaveError}
                />
              }
            />
          </Stack>

          <Divider sx={{ mb: 2 }} />

          <PrivatePatrolStatusSections
            mission={mission}
            missionStatus={vm.missionStatus}
            activeFlightId={vm.activeFlightId}
          />
        </>
      ) : null}

      <PrivatePatrolFlightDrawer
        apiBase={vm.apiBase}
        mission={mission}
        onSendMission={() => void mission.sendMission()}
        activeFlightId={vm.activeFlightId}
        missionStatus={vm.missionStatus}
        telemetry={telemetry}
        droneConnected={vm.droneConnected}
      />

      <FieldDeleteDialog
        field={vm.pendingDeleteField}
        deleting={vm.deletingField}
        onClose={vm.closeDeleteFieldDialog}
        onConfirm={() => void vm.confirmDeleteSelectedField()}
      />

      <PrivatePatrolUiNotice notice={vm.uiNotice} onClose={vm.handleUiNoticeClose} />
    </MissionWorkflowShell>
  );
}
