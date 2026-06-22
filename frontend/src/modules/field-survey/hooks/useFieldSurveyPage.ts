import { useCallback, useState } from "react";
import { getApiBaseUrl } from "../../../app/config/env";
import { getToken } from "../../../modules/session";
import { useErrors } from "../../../shared/hooks/useErrors";
import { useMissionWebsocketRuntime } from "../../../modules/mission-runtime";
import {
  useFieldTileset,
  useGeofenceLayers,
  FIELD_WORKFLOW_SCOPES,
  type FieldFeature,
} from "../../fields";
import { DEFAULT_MISSION_MAP_ENGINE, type MissionMapEngine } from "../../maps";
import type { TerraDrawEditorMode } from "../../maps";
import {
  useWorkflowFieldBoundary,
  type MissionStatus,
} from "../../mission-workflow";
import { useFieldSurveyIrrigation } from "./useFieldSurveyIrrigation";
import { useFieldSurveyMap } from "./useFieldSurveyMap";
import { useFieldSurveyMission } from "./useFieldSurveyMission";

export function useFieldSurveyPage() {
  const [lastMissionId, setLastMissionId] = useState<string | null>(null);
  const [terraDrawMode, setTerraDrawMode] =
    useState<TerraDrawEditorMode>("static");
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>(
    DEFAULT_MISSION_MAP_ENGINE,
  );

  const { errors, addError, clearErrors, dismissError } = useErrors();
  const API_BASE_CLEAN = getApiBaseUrl();

  const toAbsoluteAssetUrl = useCallback(
    (url: string) => {
      if (/^https?:\/\//i.test(url)) return url;
      return `${API_BASE_CLEAN}${url.startsWith("/") ? "" : "/"}${url}`;
    },
    [API_BASE_CLEAN],
  );

  const fieldBoundary = useWorkflowFieldBoundary({
    workflowScope: FIELD_WORKFLOW_SCOPES.fieldSurvey,
    defaultFieldName: "Field A",
    terraDrawMode,
    addError,
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
  } = useMissionWebsocketRuntime<MissionStatus>({
    apiBase: API_BASE_CLEAN,
    getTokenFn: getToken,
    onError: addError,
    alwaysConnect: true,
  });

  const trackedMissionId = activeFlightId ?? lastMissionId;
  const irrigation = useFieldSurveyIrrigation(trackedMissionId);

  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
  }, []);

  const mission = useFieldSurveyMission({
    fieldBorder: fieldBoundary.fieldBorder,
    mapEngine,
    terraDrawMode,
    addError,
    clearErrors,
    setPendingFlightId,
    setLastMissionId,
    onMissionStarted: irrigation.resetIrrigationOnMissionStart,
  });

  const map = useFieldSurveyMap({
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
    alt: mission.alt,
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
    (field: FieldFeature) => {
      fieldBoundary.selectField(field);
      map.focusFieldRing(field.ring);
    },
    [fieldBoundary, map],
  );

  const googleMapsReady =
    map.mapEngine !== "google" || (Boolean(map.apiKey) && !map.loadError);

  const cesiumZoom = mission.cesiumZoomFor(map.mapZoom);

  return {
    apiBase: API_BASE_CLEAN,
    toAbsoluteAssetUrl,
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
    irrigation,
    googleMapsReady,
    cesiumZoom,
    terraDrawMode,
    setTerraDrawMode,
    fieldBoundary,
    ...fieldBoundary,
    selectField,
    shapePrompt: fieldBoundary.shapePrompt,
  };
}
