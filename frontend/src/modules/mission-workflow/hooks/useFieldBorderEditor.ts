import { useCallback, useEffect, useRef, type MutableRefObject } from "react";
import type { TerraDraw } from "terra-draw";
import { stripClosedRing, type FieldOutDTO, type LonLat } from "../../fields";
import type { TerraDrawEditorMode } from "../../maps";
import type { TerraFeature } from "../types";

function isDrawingTerraMode(mode: TerraDrawEditorMode): boolean {
  return mode !== "static" && mode !== "select";
}

export function useFieldBorderEditor({
  setFieldBorder,
  setSelectedFieldId,
  fieldPolygonRef,
  mapRef,
  terraDrawRef,
  terraDrawMode = "static",
  onBoundaryClick,
  fieldName,
  selectedFieldId,
  fieldBorder,
  createFieldRecord,
  updateFieldRecord,
  refreshFields,
  addError,
  onSaveSuccess,
  onUpdateSuccess,
}: {
  setFieldBorder: (border: LonLat[] | null) => void;
  setSelectedFieldId: (id: number | null) => void;
  fieldPolygonRef: MutableRefObject<google.maps.Polygon | null>;
  mapRef: MutableRefObject<google.maps.Map | null>;
  terraDrawRef: MutableRefObject<TerraDraw | null>;
  terraDrawMode?: TerraDrawEditorMode;
  onBoundaryClick?: () => void;
  fieldName: string;
  selectedFieldId: number | null;
  fieldBorder: LonLat[] | null;
  createFieldRecord: (payload: {
    name: string;
    coordinates: LonLat[];
    metadata: Record<string, unknown>;
  }) => Promise<FieldOutDTO>;
  updateFieldRecord: (payload: {
    fieldId: number;
    name: string;
    coordinates: LonLat[];
  }) => Promise<FieldOutDTO>;
  refreshFields: () => void;
  addError: (message: string) => void;
  onSaveSuccess?: (field: FieldOutDTO) => void;
  onUpdateSuccess?: (field: FieldOutDTO) => void;
}) {
  const loadedRingRef = useRef<LonLat[] | null>(null);
  const boundaryClickListenerRef = useRef<google.maps.MapsEventListener | null>(null);

  const clearBoundaryClickListener = useCallback(() => {
    boundaryClickListenerRef.current?.remove();
    boundaryClickListenerRef.current = null;
  }, []);

  const isTerraGuidanceFeature = useCallback((feature: TerraFeature): boolean => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    return Boolean(
      feature?.geometry?.type === "Point" &&
        (props.coordinatePoint ||
          props.closingPoint ||
          props.snappingPoint ||
          props.selectionPoint ||
          props.midPoint)
    );
  }, []);

  const isRemovableUserDrawingFeature = useCallback(
    (feature: TerraFeature): boolean => {
      if (!feature || feature.id == null) return false;
      const mode =
        typeof feature?.properties?.mode === "string"
          ? feature.properties.mode
          : undefined;
      return mode !== "static" && !isTerraGuidanceFeature(feature);
    },
    [isTerraGuidanceFeature]
  );

  const syncFieldBorderFromSnapshot = useCallback(
    (snapshot: TerraFeature[]) => {
      const polygons = snapshot.filter(
        (f) =>
          isRemovableUserDrawingFeature(f) &&
          f?.geometry?.type === "Polygon" &&
          Array.isArray(
            ((f?.geometry as { coordinates?: unknown[] } | undefined)
              ?.coordinates ?? [])[0]
          )
      );

      if (polygons.length > 0) {
        const latest = polygons[polygons.length - 1];
        const coords = (latest.geometry?.coordinates as [number, number][][])[0];
        const ring: LonLat[] = coords.map(([lon, lat]) => [lon, lat]);
        setFieldBorder(ring);
        return;
      }

      const lines = snapshot.filter(
        (f) =>
          isRemovableUserDrawingFeature(f) &&
          f?.geometry?.type === "LineString" &&
          Array.isArray(f?.geometry?.coordinates)
      );
      if (lines.length > 0) {
        const latestLine = lines[lines.length - 1];
        const coords = latestLine.geometry?.coordinates as [number, number][];
        if (coords.length >= 3) {
          const ring: LonLat[] = coords.map(([lon, lat]) => [lon, lat]);
          setFieldBorder(ring);
          return;
        }
      }

      setFieldBorder(null);
    },
    [isRemovableUserDrawingFeature, setFieldBorder]
  );

  const polygonPathToLonLat = (poly: google.maps.Polygon): LonLat[] => {
    const path = poly.getPath();
    const pts: LonLat[] = [];
    for (let i = 0; i < path.getLength(); i++) {
      const p = path.getAt(i);
      pts.push([p.lng(), p.lat()]);
    }
    return pts;
  };

  const wirePolygonEditListeners = useCallback(
    (poly: google.maps.Polygon) => {
      const path = poly.getPath();

      const update = () => setFieldBorder(polygonPathToLonLat(poly));

      update();

      path.addListener("set_at", update);
      path.addListener("insert_at", update);
      path.addListener("remove_at", update);
    },
    [setFieldBorder]
  );

  const clearFieldBorder = useCallback(() => {
    clearBoundaryClickListener();
    loadedRingRef.current = null;
    if (fieldPolygonRef.current) {
      fieldPolygonRef.current.setMap(null);
      fieldPolygonRef.current = null;
    }
    if (terraDrawRef.current) {
      try {
        const snapshot = terraDrawRef.current.getSnapshot();
        const idsToRemove = snapshot
          .filter((f) => isRemovableUserDrawingFeature(f))
          .map((f) => String(f.id));
        if (idsToRemove.length > 0) {
          terraDrawRef.current.removeFeatures(idsToRemove);
        }
      } catch {
        // ignore
      }
    }
    setFieldBorder(null);
    setSelectedFieldId(null);
  }, [
    clearBoundaryClickListener,
    fieldPolygonRef,
    isRemovableUserDrawingFeature,
    setFieldBorder,
    setSelectedFieldId,
    terraDrawRef,
  ]);

  const saveFieldBorder = useCallback(async (): Promise<FieldOutDTO | undefined> => {
    if (!fieldBorder || fieldBorder.length < 3) {
      addError("Draw a field polygon (min 3 points) before saving.");
      return undefined;
    }
    if (!fieldName.trim()) {
      addError("Please enter a field name.");
      return undefined;
    }
    try {
      const data = await createFieldRecord({
        name: fieldName.trim(),
        coordinates: fieldBorder,
        metadata: {},
      });
      if (onSaveSuccess) {
        onSaveSuccess(data);
      } else {
        alert(`Saved field "${data.name}" (id=${data.id})`);
      }
      refreshFields();
      setSelectedFieldId(data?.id ?? null);
      return data;
    } catch (e: unknown) {
      addError(e instanceof Error ? e.message : "Failed to save field");
      return undefined;
    }
  }, [
    addError,
    createFieldRecord,
    fieldBorder,
    fieldName,
    onSaveSuccess,
    refreshFields,
    setSelectedFieldId,
  ]);

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
      if (onUpdateSuccess) {
        onUpdateSuccess(data);
      } else {
        alert(`Updated field "${data.name}" (id=${data.id})`);
      }
      refreshFields();
    } catch (e: unknown) {
      addError(e instanceof Error ? e.message : "Failed to update field");
    }
  }, [
    addError,
    fieldBorder,
    fieldName,
    onUpdateSuccess,
    refreshFields,
    selectedFieldId,
    updateFieldRecord,
  ]);

  const mountEditablePolygon = useCallback(
    (ring: LonLat[]) => {
      if (!mapRef.current || !(window as unknown as { google?: { maps?: unknown } }).google?.maps) {
        return;
      }

      if (fieldPolygonRef.current) {
        clearBoundaryClickListener();
        fieldPolygonRef.current.setMap(null);
        fieldPolygonRef.current = null;
      }

      const pts = stripClosedRing(ring);

      const poly = new google.maps.Polygon({
        paths: pts.map(([lon, lat]) => ({ lat, lng: lon })),
        editable: true,
        draggable: false,
        clickable: true,
        fillColor: "#000000",
        fillOpacity: 0,
        strokeOpacity: 0.9,
        strokeWeight: 2,
        zIndex: 20,
      });

      poly.setMap(mapRef.current);
      fieldPolygonRef.current = poly;
      wirePolygonEditListeners(poly);
    },
    [clearBoundaryClickListener, fieldPolygonRef, mapRef, wirePolygonEditListeners],
  );

  const loadRingIntoEditor = useCallback(
    (ring: LonLat[]) => {
      loadedRingRef.current = ring;
      if (isDrawingTerraMode(terraDrawMode)) return;
      mountEditablePolygon(ring);
    },
    [mountEditablePolygon, terraDrawMode],
  );

  useEffect(() => {
    if (!loadedRingRef.current) return;

    if (isDrawingTerraMode(terraDrawMode)) {
      if (fieldPolygonRef.current) {
        clearBoundaryClickListener();
        fieldPolygonRef.current.setMap(null);
      }
      return;
    }

    if (!fieldPolygonRef.current && mapRef.current) {
      mountEditablePolygon(loadedRingRef.current);
      return;
    }

    if (fieldPolygonRef.current && mapRef.current) {
      fieldPolygonRef.current.setMap(mapRef.current);
    }
  }, [
    clearBoundaryClickListener,
    fieldPolygonRef,
    mapRef,
    mountEditablePolygon,
    terraDrawMode,
  ]);

  useEffect(() => () => clearBoundaryClickListener(), [clearBoundaryClickListener]);

  useEffect(() => {
    const poly = fieldPolygonRef.current;
    if (!poly || !onBoundaryClick) return;
    clearBoundaryClickListener();
    boundaryClickListenerRef.current = poly.addListener("click", onBoundaryClick);
  }, [clearBoundaryClickListener, fieldPolygonRef, onBoundaryClick, terraDrawMode]);

  const focusRingOnMap = useCallback(
    (ring: LonLat[]) => {
      if (!mapRef.current || !window.google?.maps || ring.length < 3) return;

      const pts = stripClosedRing(ring);
      const bounds = new google.maps.LatLngBounds();
      pts.forEach(([lon, lat]) => bounds.extend({ lat, lng: lon }));

      if (!bounds.isEmpty()) {
        mapRef.current.fitBounds(bounds);
      }
    },
    [mapRef]
  );

  return {
    isRemovableUserDrawingFeature,
    syncFieldBorderFromSnapshot,
    clearFieldBorder,
    saveFieldBorder,
    updateFieldBorder,
    loadRingIntoEditor,
    focusRingOnMap,
  };
}
