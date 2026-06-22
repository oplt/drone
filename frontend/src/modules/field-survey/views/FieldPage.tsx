import { Divider, Stack } from "@mui/material";
import {
  GoogleMapEngineAlerts,
  MissionWorkflowShell,
  WorkflowTerraDrawBridge,
} from "../../mission-workflow";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import { FieldDeleteDialog } from "../../fields/components/FieldDeleteDialog";
import { FieldSurveyMapColumn } from "../components/FieldSurveyMapColumn";
import {
  FieldSurveyFlightDrawer,
  FieldSurveySetupPanel,
} from "../components/FieldSurveyPlanningSection";
import { FieldSurveyStatusSections } from "../components/FieldSurveyStatusSections";
import { useFieldSurveyPage } from "../hooks/useFieldSurveyPage";

export default function FieldPage() {
  const vm = useFieldSurveyPage();
  const { map, mission, borderEditor, irrigation } = vm;
  const telemetry = vm.telemetry as TelemetrySnapshot | null;

  return (
    <MissionWorkflowShell
      title="Field Operations"
      subtitle="Configure field routes, stream telemetry, and monitor imagery in real time."
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
          <WorkflowTerraDrawBridge
            mapReady={map.mapReady}
            mapRef={map.mapRef}
            mapEngine={map.mapEngine}
            terraDrawMode={vm.terraDrawMode}
            terraDrawRef={map.terraDrawRef}
            setTerraDrawReady={map.setTerraDrawReady}
            shapePrompt={vm.shapePrompt}
            onError={vm.addError}
          />
          <Stack spacing={2} sx={{ mb: 3 }}>
            <FieldSurveyMapColumn
              vm={vm}
              onSelectField={vm.selectField}
              setupContent={
                <FieldSurveySetupPanel
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
                  onSaveOrUpdate={
                    vm.selectedFieldId
                      ? borderEditor.updateFieldBorder
                      : borderEditor.saveFieldBorder
                  }
                  onClearBorder={borderEditor.clearFieldBorder}
                  onNewField={vm.handleNewField}
                  gridParams={mission.gridParams}
                  setGridParams={mission.setGridParams}
                  gridPreview={mission.gridPreview}
                  gridPreviewStats={mission.gridPreviewStats}
                  previewLegStats={mission.previewLegStats}
                  gridPreviewTooDense={mission.gridPreviewTooDense}
                  gridPreviewError={mission.gridPreviewError}
                  previewLoading={mission.previewLoading}
                />
              }
            />
          </Stack>

          <Divider sx={{ mb: 2 }} />

          <FieldSurveyStatusSections
            waypoints={mission.waypoints}
            alt={mission.alt}
            missionStatus={vm.missionStatus}
            activeFlightId={vm.activeFlightId}
            trackedMissionId={vm.trackedMissionId}
            irrigation={irrigation}
          />
        </>
      ) : null}

      <FieldSurveyFlightDrawer
        apiBase={vm.apiBase}
        fieldBorder={vm.fieldBorder}
        name={mission.name}
        onNameChange={mission.setName}
        altInput={mission.altInput}
        onAltInputChange={mission.handleAltitudeInputChange}
        onAltBlur={mission.normalizeAltitude}
        sending={mission.sending}
        previewLoading={mission.previewLoading}
        gridPreviewTooDense={mission.gridPreviewTooDense}
        gridPreviewError={mission.gridPreviewError}
        onSendMission={() => void mission.sendMission()}
        activeFlightId={vm.activeFlightId}
        missionStatus={vm.missionStatus}
        preflightRun={mission.preflightRun}
        telemetry={telemetry}
        droneConnected={vm.droneConnected}
      />

      <FieldDeleteDialog
        field={vm.pendingDeleteField}
        deleting={vm.deletingField}
        onClose={vm.closeDeleteFieldDialog}
        onConfirm={() => void vm.confirmDeleteSelectedField()}
      />
    </MissionWorkflowShell>
  );
}
