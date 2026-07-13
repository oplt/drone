import { Divider, Stack, Typography } from "@mui/material";
import {
  GoogleMapEngineAlerts,
  MissionWorkflowShell,
  WorkflowTerraDrawBridge,
} from "../../mission-workflow";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import { FieldDeleteDialog } from "../../fields/components/FieldDeleteDialog";
import ConfirmDialog from "../../../shared/ui/ConfirmDialog";
import { PhotogrammetryArtifactsPanel } from "../components/PhotogrammetryArtifactsPanel";
import { PhotogrammetryFieldsBlock } from "../components/PhotogrammetryFieldsBlock";
import { PhotogrammetryGridParamsSection } from "../components/PhotogrammetryGridParamsSection";
import { PhotogrammetryMapColumn } from "../components/PhotogrammetryMapColumn";
import { PhotogrammetryMissionControls } from "../components/PhotogrammetryMissionControls";
import { PhotogrammetryStatusSections } from "../components/PhotogrammetryStatusSections";
import { usePhotogrammetryPage } from "../hooks/usePhotogrammetryPage";

export default function PhotoGrammetryPage() {
  const vm = usePhotogrammetryPage();
  const { map, mission, borderEditor, mapping } = vm;
  const telemetry = vm.telemetry as TelemetrySnapshot | null;

  const open3DPlanning = () => {
    map.handleMapEngineChange("cesium");
    map.setCesiumViewMode("top");
  };

  return (
    <MissionWorkflowShell
      title="PhotoGrammetry Operations"
      subtitle="Build per-field digital twins (orthomosaic, elevation, and 3D mesh), then stream them into the tasking basemap."
      droneConnected={vm.droneConnected}
      wsConnected={vm.wsConnected}
      errors={vm.errors}
      onDismissError={vm.dismissError}
      onClearErrors={vm.clearErrors}
    >
      <PhotogrammetryArtifactsPanel />

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
            <PhotogrammetryMapColumn
              vm={vm}
              onSelectField={vm.selectField}
              setupContent={
                <Stack spacing={2}>
                  <PhotogrammetryFieldsBlock
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
                  <PhotogrammetryGridParamsSection
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
                  <Typography variant="body2" color="text.secondary">
                    Click on the map to add waypoints.
                  </Typography>
                  <PhotogrammetryMissionControls
                    embedded
                    apiBase={vm.apiBase}
                    fieldBorder={vm.fieldBorder}
                    preflightRun={mission.preflightRun}
                    telemetry={telemetry}
                    droneConnected={vm.droneConnected}
                    missionStatus={vm.missionStatus}
                    activeFlightId={vm.activeFlightId}
                    mission={mission}
                    mapping={mapping}
                    selectedFieldId={vm.selectedFieldId}
                    onOpen3DPlanning={open3DPlanning}
                  />
                </Stack>
              }
            />
          </Stack>

          <Divider sx={{ mb: 2 }} />

          <PhotogrammetryStatusSections
            waypoints={mission.waypoints}
            alt={mission.alt}
            missionStatus={vm.missionStatus}
            activeFlightId={vm.activeFlightId}
          />
        </>
      ) : null}

      <FieldDeleteDialog
        field={vm.pendingDeleteField}
        deleting={vm.deletingField}
        onClose={vm.closeDeleteFieldDialog}
        onConfirm={() => void vm.confirmDeleteSelectedField()}
      />
      <ConfirmDialog
        open={mapping.pendingDeleteJobId != null}
        title="Delete mapping job?"
        description={`Delete mapping job #${mapping.pendingDeleteJobId ?? ""}? This cannot be undone.`}
        confirmLabel="Delete job"
        confirmColor="error"
        loading={mapping.busy}
        onCancel={mapping.closeDeleteJobDialog}
        onConfirm={() => void mapping.confirmDeleteJob()}
      />
    </MissionWorkflowShell>
  );
}
