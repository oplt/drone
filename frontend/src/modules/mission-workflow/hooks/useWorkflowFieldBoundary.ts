import { useCallback, useMemo, useRef, useState } from "react";
import type { TerraDraw } from "terra-draw";
import {
  computeAreaHa,
  computeCentroid,
  useFields,
  type FieldFeature,
  type FieldOutDTO,
  type FieldWorkflowScope,
  type LonLat,
} from "../../fields";
import type { TerraDrawEditorMode } from "../../maps";
import { useFieldBorderEditor } from "./useFieldBorderEditor";
import { useMapShapeActionPrompt } from "./useMapShapeActionPrompt";

export type FieldIdPersistence = {
  read: () => number | null;
  write: (id: number | null) => void;
};

export function useWorkflowFieldBoundary({
  workflowScope,
  defaultFieldName,
  terraDrawMode,
  addError,
  onSaveSuccess,
  onUpdateSuccess,
  onDeleteSuccess,
  persistFieldId,
}: {
  workflowScope: FieldWorkflowScope;
  defaultFieldName: string;
  terraDrawMode: TerraDrawEditorMode;
  addError: (message: string) => void;
  onSaveSuccess?: (field: FieldOutDTO) => void;
  onUpdateSuccess?: (field: FieldOutDTO) => void;
  onDeleteSuccess?: (fieldName: string) => void;
  persistFieldId?: FieldIdPersistence;
}) {
  const [fieldName, setFieldName] = useState(defaultFieldName);
  const [fieldBorder, setFieldBorder] = useState<LonLat[] | null>(null);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);
  const [pendingDeleteField, setPendingDeleteField] =
    useState<FieldFeature | null>(null);

  const mapRef = useRef<google.maps.Map | null>(null);
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const fieldPolygonRef = useRef<google.maps.Polygon | null>(null);
  const notifyShapeSelectedRef = useRef<() => void>(() => {});

  const {
    fields,
    loading: loadingFields,
    refresh: refreshFields,
    createField: createFieldRecord,
    updateField: updateFieldRecord,
    deleteField: deleteFieldRecord,
    saving: savingField,
    deleting: deletingField,
  } = useFields(workflowScope);

  const handleSaveSuccess = useCallback(
    (field: FieldOutDTO) => {
      setSelectedFieldId(field?.id ?? null);
      if (field?.id != null) {
        persistFieldId?.write(field.id);
      }
      onSaveSuccess?.(field);
    },
    [onSaveSuccess, persistFieldId],
  );

  const handleUpdateSuccess = useCallback(
    (field: FieldOutDTO) => {
      if (selectedFieldId != null) {
        persistFieldId?.write(selectedFieldId);
      }
      onUpdateSuccess?.(field);
    },
    [onUpdateSuccess, persistFieldId, selectedFieldId],
  );

  const borderEditor = useFieldBorderEditor({
    setFieldBorder,
    setSelectedFieldId,
    fieldPolygonRef,
    mapRef,
    terraDrawRef,
    terraDrawMode,
    onBoundaryClick: () => notifyShapeSelectedRef.current(),
    fieldName,
    selectedFieldId,
    fieldBorder,
    createFieldRecord,
    updateFieldRecord,
    refreshFields,
    addError,
    onSaveSuccess: handleSaveSuccess,
    onUpdateSuccess: handleUpdateSuccess,
  });

  const shapePrompt = useMapShapeActionPrompt({
    terraDrawRef,
    syncSnapshot: borderEditor.syncFieldBorderFromSnapshot,
  });
  notifyShapeSelectedRef.current = shapePrompt.notifyShapeSelected;

  const selectedField = useMemo(
    () =>
      selectedFieldId == null
        ? null
        : (fields.find((field) => field.id === selectedFieldId) ?? null),
    [fields, selectedFieldId],
  );

  const metrics = useMemo(() => {
    if (!fieldBorder || fieldBorder.length < 3) return null;
    return {
      areaHa: computeAreaHa(fieldBorder),
      centroid: computeCentroid(fieldBorder),
    };
  }, [fieldBorder]);

  const selectField = useCallback(
    (field: FieldFeature) => {
      setSelectedFieldId(field.id);
      persistFieldId?.write(field.id);
      setFieldName(field.name);
      setFieldBorder(field.ring);
      borderEditor.loadRingIntoEditor(field.ring);
      borderEditor.focusRingOnMap(field.ring);
    },
    [borderEditor, persistFieldId],
  );

  const focusSelectedField = useCallback(() => {
    if (!selectedField) return;
    borderEditor.focusRingOnMap(selectedField.ring);
  }, [borderEditor, selectedField]);

  const handleSavedFieldSelect = useCallback(
    (fieldId: number | null) => {
      if (fieldId == null) {
        persistFieldId?.write(null);
        borderEditor.clearFieldBorder();
        shapePrompt.resetBoundaryDrawSession();
        return;
      }
      const field = fields.find((item) => item.id === fieldId);
      if (field) selectField(field);
    },
    [borderEditor, fields, persistFieldId, selectField, shapePrompt],
  );

  const handleNewField = useCallback(() => {
    setSelectedFieldId(null);
    persistFieldId?.write(null);
    setFieldName(defaultFieldName);
    borderEditor.clearFieldBorder();
    shapePrompt.resetBoundaryDrawSession();
  }, [borderEditor, defaultFieldName, persistFieldId, shapePrompt]);

  const requestDeleteSelectedField = useCallback(() => {
    if (selectedFieldId == null) {
      addError("Select a saved field to delete.");
      return;
    }
    const targetField = fields.find((field) => field.id === selectedFieldId) ?? null;
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
      setFieldName(defaultFieldName);
      setPendingDeleteField(null);
      shapePrompt.resetBoundaryDrawSession();
      onDeleteSuccess?.(pendingDeleteField.name);
    } catch (error: unknown) {
      addError(error instanceof Error ? error.message : "Failed to delete field");
    }
  }, [
    addError,
    borderEditor,
    defaultFieldName,
    deleteFieldRecord,
    onDeleteSuccess,
    pendingDeleteField,
    shapePrompt,
  ]);

  const saveFromShapePrompt = useCallback(async () => {
    if (selectedFieldId != null) {
      await borderEditor.updateFieldBorder();
    } else {
      await borderEditor.saveFieldBorder();
    }
    shapePrompt.closePrompt();
  }, [borderEditor, selectedFieldId, shapePrompt]);

  return {
    fieldName,
    setFieldName,
    fieldBorder,
    setFieldBorder,
    selectedFieldId,
    setSelectedFieldId,
    selectedField,
    metrics,
    fields,
    loadingFields,
    refreshFields,
    savingField,
    deletingField,
    pendingDeleteField,
    mapRef,
    terraDrawRef,
    fieldPolygonRef,
    borderEditor,
    shapePrompt,
    saveFromShapePrompt,
    handleShapePromptSave: saveFromShapePrompt,
    selectField,
    focusSelectedField,
    handleSavedFieldSelect,
    handleNewField,
    requestDeleteSelectedField,
    closeDeleteFieldDialog,
    confirmDeleteSelectedField,
    saveFieldBorder: borderEditor.saveFieldBorder,
    updateFieldBorder: borderEditor.updateFieldBorder,
    createFieldRecord,
  };
}

export type WorkflowFieldBoundaryVm = ReturnType<typeof useWorkflowFieldBoundary>;
