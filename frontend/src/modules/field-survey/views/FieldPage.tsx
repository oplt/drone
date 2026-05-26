import { Divider, Stack, Typography } from "@mui/material";
import { TerraDrawController } from "../../maps";
import {
  GoogleMapEngineAlerts,
  MissionWorkflowShell,
} from "../../mission-workflow";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import { FieldDeleteDialog } from "../components/FieldDeleteDialog";
import { FieldSurveyGridParamsSection } from "../components/FieldSurveyGridParamsSection";
import { FieldSurveyMapColumn } from "../components/FieldSurveyMapColumn";
import {
  FieldSurveyFieldsBlock,
  FieldSurveyMissionControls,
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
          <TerraDrawController
            map={map.mapReady ? map.mapRef.current : null}
            enabled={map.mapEngine === "google"}
            mode={map.terraDrawMode}
            drawRef={map.terraDrawRef}
            onReadyChange={map.setTerraDrawReady}
            onSnapshotChange={borderEditor.syncFieldBorderFromSnapshot}
            onError={vm.addError}
          />
          <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ mb: 3 }}>
            <Stack sx={{ flex: 1 }} spacing={2}>
              <FieldSurveyMapColumn vm={vm} onSelectField={vm.selectField} />
              <FieldSurveyFieldsBlock
                fields={vm.fields}
                selectedFieldId={vm.selectedFieldId}
                selectedField={vm.selectedField}
                loadingFields={vm.loadingFields}
                deletingField={vm.deletingField}
                onSelectField={vm.handleSavedFieldSelect}
                onRefreshFields={vm.refreshFields}
                onFocusSelected={() =>
                  vm.selectedField &&
                  borderEditor.focusRingOnMap(vm.selectedField.ring)
                }
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
              />
              <FieldSurveyGridParamsSection
                gridParams={mission.gridParams}
                setGridParams={mission.setGridParams}
                fieldBorder={vm.fieldBorder}
                gridPreview={mission.gridPreview}
                gridPreviewStats={mission.gridPreviewStats}
                previewLegStats={mission.previewLegStats}
                gridPreviewTooDense={mission.gridPreviewTooDense}
                gridPreviewError={mission.gridPreviewError}
                previewLoading={mission.previewLoading}
              />
              <Typography variant="body2" sx={{ mt: 1 }}>
                Click on the map to add waypoints.
              </Typography>
            </Stack>

            <FieldSurveyMissionControls
              controlFrameExpanded={vm.controlFrameExpanded}
              onControlFrameExpandedChange={vm.setControlFrameExpanded}
              apiBase={vm.apiBase}
              fieldBorder={vm.fieldBorder}
              preflightRun={mission.preflightRun}
              telemetry={telemetry}
              droneConnected={vm.droneConnected}
              missionStatus={vm.missionStatus}
              activeFlightId={vm.activeFlightId}
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

      <FieldDeleteDialog
        field={vm.pendingDeleteField}
        deleting={vm.deletingField}
        onClose={vm.closeDeleteFieldDialog}
        onConfirm={() => void vm.confirmDeleteSelectedField()}
      />
    </MissionWorkflowShell>
  );
}
