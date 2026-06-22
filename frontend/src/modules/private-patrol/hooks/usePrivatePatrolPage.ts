import { useCallback, useEffect, useState } from "react";
import { getApiBaseUrl } from "../../../app/config/env";
import { getToken } from "../../../modules/session";
import { useErrors } from "../../../shared/hooks/useErrors";
import { useMissionWebsocketRuntime } from "../../../modules/mission-runtime";
import {
  useFieldTileset,
  useGeofenceLayers,
  FIELD_WORKFLOW_SCOPES,
  type FieldOutDTO,
} from "../../fields";
import { DEFAULT_MISSION_MAP_ENGINE, type MissionMapEngine } from "../../maps";
import type { TerraDrawEditorMode } from "../../maps";
import { useWorkflowFieldBoundary } from "../../mission-workflow";
import type {
  NoticeSeverity,
  PrivatePatrolMissionStatus,
  UiNotice,
} from "../types";
import {
  readPropertyPatrolFieldId,
  writePropertyPatrolFieldId,
} from "../propertyGeofencePreference";
import { usePrivatePatrolMap } from "./usePrivatePatrolMap";
import { usePrivatePatrolMission } from "./usePrivatePatrolMission";
import { useEventTriggerConfigPersistence } from "./useEventTriggerConfigPersistence";

export function usePrivatePatrolPage() {
  const [lastMissionId, setLastMissionId] = useState<string | null>(null);
  const [terraDrawMode, setTerraDrawMode] =
    useState<TerraDrawEditorMode>("static");
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>(
    DEFAULT_MISSION_MAP_ENGINE,
  );
  const [uiNotice, setUiNotice] = useState<UiNotice>({
    open: false,
    severity: "success",
    message: "",
  });

  const { errors, addError, clearErrors, dismissError } = useErrors();

  const API_BASE_CLEAN = getApiBaseUrl();

  const showUiNotice = useCallback(
    (message: string, severity: NoticeSeverity = "success") => {
      setUiNotice({ open: true, severity, message });
    },
    [],
  );

  const handleUiNoticeClose = useCallback(
    (_event?: unknown, reason?: string) => {
      if (reason === "clickaway") return;
      setUiNotice((prev) => ({ ...prev, open: false }));
    },
    [],
  );

  const fieldBoundary = useWorkflowFieldBoundary({
    workflowScope: FIELD_WORKFLOW_SCOPES.propertyPatrol,
    defaultFieldName: "Main Property",
    terraDrawMode,
    addError,
    persistFieldId: {
      read: readPropertyPatrolFieldId,
      write: writePropertyPatrolFieldId,
    },
    onSaveSuccess: (field: FieldOutDTO) => {
      showUiNotice(`Saved field "${field.name}" (#${field.id})`);
    },
    onUpdateSuccess: (field: FieldOutDTO) => {
      showUiNotice(`Updated field "${field.name}" (#${field.id})`);
    },
    onDeleteSuccess: (fieldName) => {
      showUiNotice(`Deleted field "${fieldName}"`);
    },
  });

  const { exclusionZones } = useGeofenceLayers();
  const { tilesetUrl: fieldTilesetUrl } = useFieldTileset(
    fieldBoundary.selectedFieldId,
  );

  const {
    missionStatus,
    activeFlightId,
    setPendingFlightId,
    telemetry,
    wsConnected,
    droneConnected,
  } = useMissionWebsocketRuntime<PrivatePatrolMissionStatus>({
    apiBase: API_BASE_CLEAN,
    getTokenFn: getToken,
    onError: addError,
    alwaysConnect: true,
  });

  const trackedMissionId = activeFlightId ?? lastMissionId;

  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
  }, []);

  const mission = usePrivatePatrolMission({
    fieldBorder: fieldBoundary.fieldBorder,
    mapEngine,
    terraDrawMode,
    addError,
    clearErrors,
    setPendingFlightId,
    setLastMissionId,
    showUiNotice,
    missionStatus,
    activeFlightId,
  });

  const eventTriggerConfig = useEventTriggerConfigPersistence({
    selectedFieldId: fieldBoundary.selectedFieldId,
    gridParams: mission.gridParams,
    setGridParams: mission.setGridParams,
    cruiseAlt: mission.alt,
    setCruiseAlt: mission.setAlt,
    setCruiseAltInput: mission.setAltInput,
  });

  const map = usePrivatePatrolMap({
    apiBase: API_BASE_CLEAN,
    wsConnected,
    droneConnected,
    telemetry,
    activeFlightId,
    fieldBorder: fieldBoundary.fieldBorder,
    setFieldBorder: fieldBoundary.setFieldBorder,
    setSelectedFieldId: fieldBoundary.setSelectedFieldId,
    fieldTilesetUrl,
    waypoints: mission.waypoints,
    setWaypoints: mission.setWaypoints,
    eventLocation: mission.eventLocation,
    setEventLocation: mission.setEventLocation,
    alt: mission.alt,
    gridParams: mission.gridParams,
    drawMode: mission.drawMode,
    setDrawMode: mission.setDrawMode,
    terraDrawMode,
    setTerraDrawMode,
    syncFieldBorderFromSnapshot: fieldBoundary.borderEditor.syncFieldBorderFromSnapshot,
    isRemovableUserDrawingFeature:
      fieldBoundary.borderEditor.isRemovableUserDrawingFeature,
    loadRingIntoEditor: fieldBoundary.borderEditor.loadRingIntoEditor,
    selectedField: fieldBoundary.selectedField,
    mapEngine,
    addError,
    onMapEngineChange: handleMapEngineChange,
    fieldPolygonRef: fieldBoundary.fieldPolygonRef,
    terraDrawRef: fieldBoundary.terraDrawRef,
    onBoundaryDrawStarted: fieldBoundary.shapePrompt.notifyBoundaryDrawStarted,
    resetBoundaryDrawSession: fieldBoundary.shapePrompt.resetBoundaryDrawSession,
  });

  const selectField = useCallback(
    (field: Parameters<typeof fieldBoundary.selectField>[0]) => {
      fieldBoundary.selectField(field);
      map.focusFieldRing(field.ring);
    },
    [fieldBoundary, map],
  );

  useEffect(() => {
    if (fieldBoundary.selectedFieldId != null || fieldBoundary.fields.length === 0) {
      return;
    }
    if (fieldBoundary.fieldBorder && fieldBoundary.fieldBorder.length >= 3) {
      return;
    }
    const storedFieldId = readPropertyPatrolFieldId();
    if (storedFieldId == null) return;
    const field = fieldBoundary.fields.find((item) => item.id === storedFieldId);
    if (field) selectField(field);
  }, [
    fieldBoundary.fields,
    fieldBoundary.selectedFieldId,
    selectField,
  ]);

  const focusSelectedField = useCallback(() => {
    if (!fieldBoundary.selectedField) return;
    map.focusFieldRing(fieldBoundary.selectedField.ring);
  }, [fieldBoundary.selectedField, map]);

  const googleMapsReady =
    map.mapEngine !== "google" || (Boolean(map.apiKey) && !map.loadError);

  const cesiumZoom = mission.cesiumZoomFor(map.mapZoom);

  return {
    apiBase: API_BASE_CLEAN,
    errors,
    addError,
    dismissError,
    clearErrors,
    droneConnected,
    wsConnected,
    missionStatus,
    activeFlightId,
    trackedMissionId,
    telemetry,
    fieldTilesetUrl,
    exclusionZones,
    mission,
    map,
    googleMapsReady,
    cesiumZoom,
    terraDrawMode,
    setTerraDrawMode,
    uiNotice,
    handleUiNoticeClose,
    eventTriggerIntegration: eventTriggerConfig.eventTriggerIntegration,
    eventTriggerSaving: eventTriggerConfig.eventTriggerSaving,
    eventTriggerSaveError: eventTriggerConfig.eventTriggerSaveError,
    fieldBoundary,
    ...fieldBoundary,
    selectField,
    focusSelectedField,
    shapePrompt: fieldBoundary.shapePrompt,
  };
}
