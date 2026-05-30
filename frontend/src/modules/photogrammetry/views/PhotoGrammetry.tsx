import { Divider, Stack, Typography } from "@mui/material";
import { TerraDrawController } from "../../maps";
import {
  GoogleMapEngineAlerts,
  MissionWorkflowShell,
} from "../../mission-workflow";
import type { TelemetrySnapshot } from "../../mission-runtime/types/runtime";
import { FieldDeleteDialog } from "../../field-survey/components/FieldDeleteDialog";
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
          <TerraDrawController
            map={map.mapReady ? map.mapRef.current : null}
            enabled={map.mapEngine === "google"}
            mode={vm.terraDrawMode}
            drawRef={map.terraDrawRef}
            onReadyChange={map.setTerraDrawReady}
            onSnapshotChange={borderEditor.syncFieldBorderFromSnapshot}
            onError={vm.addError}
          />
          <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ mb: 3 }}>
            <Stack sx={{ flex: 1 }} spacing={2}>
              <PhotogrammetryMapColumn vm={vm} onSelectField={vm.selectField} />
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
              <Typography variant="body2" sx={{ mt: 1 }}>
                Click on the map to add waypoints.
              </Typography>
            </Stack>

            <PhotogrammetryMissionControls
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
    </MissionWorkflowShell>
  );
}
