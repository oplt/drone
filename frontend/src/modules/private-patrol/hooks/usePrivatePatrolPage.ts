import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TerraDraw } from "terra-draw";
import { getToken } from "../../../modules/session";
import { useErrors } from "../../../shared/hooks/useErrors";
import { useMissionWebsocketRuntime } from "../../../modules/mission-runtime";
import {
  computeAreaHa,
  computeCentroid,
  useFields,
  useFieldTileset,
  useGeofenceLayers,
  type FieldFeature,
  type LonLat,
} from "../../fields";
import { DEFAULT_MISSION_MAP_ENGINE, type MissionMapEngine } from "../../maps";
import type { TerraDrawEditorMode } from "../../maps";
import { useFieldBorderEditor } from "../../mission-workflow";
import type { NoticeSeverity, PrivatePatrolMissionStatus, UiNotice } from "../types";
import { usePrivatePatrolMap } from "./usePrivatePatrolMap";
import { usePrivatePatrolMission } from "./usePrivatePatrolMission";

export function usePrivatePatrolPage() {
  const [controlFrameExpanded, setControlFrameExpanded] = useState(true);
  const [fieldName, setFieldName] = useState("Field A");
  const [fieldBorder, setFieldBorder] = useState<LonLat[] | null>(null);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);
  const [pendingDeleteField, setPendingDeleteField] = useState<FieldFeature | null>(null);
  const [terraDrawMode, setTerraDrawMode] = useState<TerraDrawEditorMode>("static");
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>(DEFAULT_MISSION_MAP_ENGINE);
  const [uiNotice, setUiNotice] = useState<UiNotice>({
    open: false,
    severity: "success",
    message: "",
  });

  const mapRef = useRef<google.maps.Map | null>(null);
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const fieldPolygonRef = useRef<google.maps.Polygon | null>(null);

  const { errors, addError, clearErrors, dismissError } = useErrors();

  const API_BASE_RAW = import.meta.env.VITE_API_BASE_URL ?? "";
  const API_BASE_CLEAN = (API_BASE_RAW || "http://localhost:8000").replace(/\/$/, "");

  const showUiNotice = useCallback((message: string, severity: NoticeSeverity = "success") => {
    setUiNotice({ open: true, severity, message });
  }, []);

  const handleUiNoticeClose = useCallback((_event?: unknown, reason?: string) => {
    if (reason === "clickaway") return;
    setUiNotice((prev) => ({ ...prev, open: false }));
  }, []);

  const {
    fields,
    loading: loadingFields,
    refresh: refreshFields,
    createField: createFieldRecord,
    updateField: updateFieldRecord,
    deleteField: deleteFieldRecord,
    saving: savingField,
    deleting: deletingField,
  } = useFields();

  const { exclusionZones } = useGeofenceLayers();
  const { tilesetUrl: fieldTilesetUrl } = useFieldTileset(selectedFieldId);

  const {
    missionStatus,
    activeFlightId,
    setPendingFlightId,
    telemetry,
    wsConnected,
    disconnect,
    droneConnected,
  } = useMissionWebsocketRuntime<PrivatePatrolMissionStatus>({
    apiBase: API_BASE_CLEAN,
    getTokenFn: getToken,
    onError: addError,
  });

  const borderEditor = useFieldBorderEditor({
    setFieldBorder,
    setSelectedFieldId,
    fieldPolygonRef,
    mapRef,
    terraDrawRef,
    fieldName,
    selectedFieldId,
    fieldBorder,
    createFieldRecord,
    updateFieldRecord,
    refreshFields,
    addError,
  });

  const saveFieldBorder = useCallback(async () => {
    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw a field polygon (min 3 points) before saving.");
      return;
    }
    if (!fieldName.trim()) {
      addError("Please enter a field name.");
      return;
    }
    try {
      const data = await createFieldRecord({
        name: fieldName.trim(),
        coordinates: fieldBorder,
        metadata: {},
      });
      showUiNotice(`Saved field "${data.name}" (#${data.id})`);
      setSelectedFieldId(data?.id ?? null);
    } catch (e: unknown) {
      addError(e instanceof Error ? e.message : "Failed to save field");
    }
  }, [addError, createFieldRecord, fieldBorder, fieldName, showUiNotice]);

  const updateFieldBorder = useCallback(async () => {
    if (selectedFieldId == null) {
      addError("Select a field to update.");
      return;
    }
    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw/edit a field polygon (min 3 points) before updating.");
      return;
    }
    if (!fieldName.trim()) {
      addError("Please enter a field name.");
      return;
    }
    try {
      const data = await updateFieldRecord({
        fieldId: selectedFieldId,
        name: fieldName.trim(),
        coordinates: fieldBorder,
      });
      showUiNotice(`Updated field "${data.name}" (#${data.id})`);
    } catch (e: unknown) {
      addError(e instanceof Error ? e.message : "Failed to update field");
    }
  }, [addError, fieldBorder, fieldName, selectedFieldId, showUiNotice, updateFieldRecord]);

  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
  }, []);

  const mission = usePrivatePatrolMission({
    fieldBorder,
    mapEngine,
    terraDrawMode,
    addError,
    clearErrors,
    setPendingFlightId,
    showUiNotice,
  });

  const map = usePrivatePatrolMap({
    apiBase: API_BASE_CLEAN,
    wsConnected,
    telemetry,
    activeFlightId,
    fieldBorder,
    setFieldBorder,
    setSelectedFieldId,
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
    syncFieldBorderFromSnapshot: borderEditor.syncFieldBorderFromSnapshot,
    isRemovableUserDrawingFeature: borderEditor.isRemovableUserDrawingFeature,
    loadRingIntoEditor: borderEditor.loadRingIntoEditor,
    focusRingOnMap: borderEditor.focusRingOnMap,
    selectedField:
      selectedFieldId == null
        ? null
        : fields.find((f) => f.id === selectedFieldId) ?? null,
    mapEngine,
    addError,
    onMapEngineChange: handleMapEngineChange,
    fieldPolygonRef,
    terraDrawRef,
  });

  const selectedField = useMemo(
    () =>
      selectedFieldId == null
        ? null
        : fields.find((f) => f.id === selectedFieldId) ?? null,
    [fields, selectedFieldId]
  );

  const metrics = useMemo(() => {
    if (!fieldBorder || fieldBorder.length < 3) return null;
    return {
      areaHa: computeAreaHa(fieldBorder),
      centroid: computeCentroid(fieldBorder),
    };
  }, [fieldBorder]);

  const selectField = useCallback(
    (f: FieldFeature) => {
      map.handleMapEngineChange("google");
      setSelectedFieldId(f.id);
      setFieldName(f.name);
      setFieldBorder(f.ring);
      borderEditor.loadRingIntoEditor(f.ring);
      borderEditor.focusRingOnMap(f.ring);
    },
    [borderEditor, map]
  );

  const handleSavedFieldSelect = useCallback(
    (fieldId: number | null) => {
      if (fieldId == null) {
        borderEditor.clearFieldBorder();
        return;
      }
      const field = fields.find((f) => f.id === fieldId);
      if (field) selectField(field);
    },
    [borderEditor, fields, selectField]
  );

  const handleNewField = useCallback(() => {
    setSelectedFieldId(null);
    setFieldName("Field A");
    borderEditor.clearFieldBorder();
  }, [borderEditor]);

  const requestDeleteSelectedField = useCallback(() => {
    if (selectedFieldId == null) {
      addError("Select a saved field to delete.");
      return;
    }
    const targetField = fields.find((f) => f.id === selectedFieldId) ?? null;
    if (!targetField) {
      addError("Selected field could not be resolved.");
      return;
    }
    setPendingDeleteField(targetField);
  }, [addError, fields, selectedFieldId]);

  const closeDeleteFieldDialog = useCallback(() => {
    if (deletingField) return;
    setPendingDeleteField(null);
  }, [deletingField]);

  const confirmDeleteSelectedField = useCallback(async () => {
    if (!pendingDeleteField) return;
    try {
      await deleteFieldRecord(pendingDeleteField.id);
      borderEditor.clearFieldBorder();
      setFieldName("Field A");
      setPendingDeleteField(null);
      showUiNotice(`Deleted field "${pendingDeleteField.name}"`);
    } catch (e: unknown) {
      addError(e instanceof Error ? e.message : "Failed to delete field");
    }
  }, [addError, borderEditor, deleteFieldRecord, pendingDeleteField, showUiNotice]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  const googleMapsReady =
    map.mapEngine !== "google" || (Boolean(map.apiKey) && !map.loadError);

  const cesiumZoom = mission.cesiumZoomFor(map.mapZoom);

  return {
    apiBase: API_BASE_CLEAN,
    controlFrameExpanded,
    setControlFrameExpanded,
    errors,
    addError,
    dismissError,
    clearErrors,
    droneConnected,
    wsConnected,
    missionStatus,
    activeFlightId,
    telemetry,
    fields,
    fieldTilesetUrl,
    exclusionZones,
    selectedFieldId,
    selectedField,
    fieldName,
    setFieldName,
    fieldBorder,
    setFieldBorder,
    metrics,
    selectField,
    loadingFields,
    refreshFields,
    savingField,
    deletingField,
    pendingDeleteField,
    handleSavedFieldSelect,
    handleNewField,
    requestDeleteSelectedField,
    closeDeleteFieldDialog,
    confirmDeleteSelectedField,
    saveFieldBorder,
    updateFieldBorder,
    borderEditor,
    mission,
    map,
    googleMapsReady,
    cesiumZoom,
    terraDrawMode,
    setTerraDrawMode,
    uiNotice,
    handleUiNoticeClose,
  };
}
