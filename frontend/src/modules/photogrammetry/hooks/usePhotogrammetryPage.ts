import { useCallback, useState } from "react";
import { getApiBaseUrl } from "../../../app/config/env";
import { getToken } from "../../../modules/session";
import { useErrors } from "../../../shared/hooks/useErrors";
import { useMissionWebsocketRuntime } from "../../../modules/mission-runtime";
import {
  useFieldTileset,
  useGeofenceLayers,
  FIELD_WORKFLOW_SCOPES,
} from "../../fields";
import {
  DEFAULT_MISSION_MAP_ENGINE,
  type MissionMapEngine,
  type TerraDrawEditorMode,
} from "../../maps";
import {
  useWorkflowFieldBoundary,
  type MissionStatus,
} from "../../mission-workflow";
import { usePhotogrammetryMap } from "./usePhotogrammetryMap";
import { usePhotogrammetryMapping } from "./usePhotogrammetryMapping";
import { usePhotogrammetryMission } from "./usePhotogrammetryMission";

export function usePhotogrammetryPage() {
  const [terraDrawMode, setTerraDrawMode] =
    useState<TerraDrawEditorMode>("static");
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>(
    DEFAULT_MISSION_MAP_ENGINE,
  );

  const { errors, addError, clearErrors, dismissError } = useErrors();

  const API_BASE_CLEAN = getApiBaseUrl();

  const fieldBoundary = useWorkflowFieldBoundary({
    workflowScope: FIELD_WORKFLOW_SCOPES.photogrammetry,
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

  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
  }, []);

  const mission = usePhotogrammetryMission({
    fieldBorder: fieldBoundary.fieldBorder,
    mapEngine,
    terraDrawMode,
    addError,
    clearErrors,
    setPendingFlightId,
  });

  const map = usePhotogrammetryMap({
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
    loadRingIntoEditor: fieldBoundary.borderEditor.loadRingIntoEditor,
    focusRingOnMap: fieldBoundary.borderEditor.focusRingOnMap,
    selectedField: fieldBoundary.selectedField,
    mapEngine,
    addError,
    onMapEngineChange: handleMapEngineChange,
    fieldPolygonRef: fieldBoundary.fieldPolygonRef,
    terraDrawRef: fieldBoundary.terraDrawRef,
    onBoundaryDrawStarted: fieldBoundary.shapePrompt.notifyBoundaryDrawStarted,
    resetBoundaryDrawSession: fieldBoundary.shapePrompt.resetBoundaryDrawSession,
  });

  const ensureFieldForMapping = useCallback(
    async (options?: { announce?: boolean }) => {
      if (!fieldBoundary.fieldBorder || fieldBoundary.fieldBorder.length < 3) {
        throw new Error(
          "Draw a field polygon (min 3 points) before continuing.",
        );
      }
      if (!fieldBoundary.fieldName.trim()) {
        throw new Error("Please enter a field name before continuing.");
      }

      const data = await fieldBoundary.createFieldRecord({
        name: fieldBoundary.fieldName.trim(),
        coordinates: fieldBoundary.fieldBorder,
        metadata: {},
      });
      fieldBoundary.setSelectedFieldId(data?.id ?? null);

      if (options?.announce ?? true) {
        alert(`Saved field "${data.name}" (id=${data.id})`);
      }

      return data;
    },
    [fieldBoundary],
  );

  const mapping = usePhotogrammetryMapping({
    selectedFieldId: fieldBoundary.selectedFieldId,
    setSelectedFieldId: fieldBoundary.setSelectedFieldId,
    fieldBorder: fieldBoundary.fieldBorder,
    fieldName: fieldBoundary.fieldName,
    ensureFieldForMapping,
    onJobReady: () => {
      map.handleMapEngineChange("cesium");
      map.setCesiumViewMode("top");
    },
    addError,
  });

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
    telemetry,
    fieldTilesetUrl,
    exclusionZones,
    mission,
    map,
    mapping,
    googleMapsReady,
    cesiumZoom,
    terraDrawMode,
    setTerraDrawMode,
    fieldBoundary,
    ...fieldBoundary,
    shapePrompt: fieldBoundary.shapePrompt,
  };
}
