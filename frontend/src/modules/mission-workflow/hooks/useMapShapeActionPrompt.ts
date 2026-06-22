import { useCallback, useRef, useState, type MutableRefObject } from "react";
import type { TerraDraw } from "terra-draw";
import type { TerraDrawFeature } from "../../maps/components/TerraDrawController";
import {
  findTerraDrawFeature,
  hasUserDrawnBoundaryShape,
  isActiveBoundaryDrawFeature,
  isUserDrawnBoundaryShape,
  shouldOpenShapePromptOnSelection,
} from "../utils/mapShapePromptUtils";
import { deleteMainDrawnShape } from "../utils/terraDrawDrawingActions";

function featureDrawMode(
  feature: TerraDrawFeature | undefined,
): string | undefined {
  const mode = feature?.properties?.mode;
  return typeof mode === "string" ? mode : undefined;
}

const DRAW_ACTIVITY_EVENTS = new Set(["create", "created", "update", "updated"]);

export function useMapShapeActionPrompt({
  terraDrawRef,
  syncSnapshot,
}: {
  terraDrawRef: MutableRefObject<TerraDraw | null>;
  syncSnapshot: (snapshot: TerraDrawFeature[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [flatBoundarySelected, setFlatBoundarySelected] = useState(false);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | number | null>(
    null,
  );
  const selectedFeatureIdRef = useRef<string | number | null>(null);
  const boundaryDrawSessionStartedRef = useRef(false);
  const armedGoogleFeatureIdRef = useRef<string | number | null>(null);

  const openPrompt = useCallback(() => setOpen(true), []);
  const closePrompt = useCallback(() => setOpen(false), []);

  const resetBoundaryDrawSession = useCallback(() => {
    boundaryDrawSessionStartedRef.current = false;
    setFlatBoundarySelected(false);
  }, []);

  const notifyBoundaryDrawStarted = useCallback(() => {
    if (boundaryDrawSessionStartedRef.current) return;
    boundaryDrawSessionStartedRef.current = true;
    setFlatBoundarySelected(true);
    setOpen(true);
  }, []);

  const handleSnapshotChange = useCallback(
    (snapshot: TerraDrawFeature[]) => {
      syncSnapshot(snapshot);
    },
    [syncSnapshot],
  );

  const handleChangeEvent = useCallback(
    (event: string, snapshot: TerraDrawFeature[]) => {
      syncSnapshot(snapshot);

      if (!DRAW_ACTIVITY_EVENTS.has(event)) return;
      if (boundaryDrawSessionStartedRef.current) return;
      if (!snapshot.some(isActiveBoundaryDrawFeature)) return;

      boundaryDrawSessionStartedRef.current = true;
      armedGoogleFeatureIdRef.current = null;
      setFlatBoundarySelected(true);
      setOpen(true);
    },
    [syncSnapshot],
  );

  const handleSelectionChange = useCallback(
    (selectedId: string | number | null) => {
      selectedFeatureIdRef.current = selectedId;
      setSelectedFeatureId(selectedId);
      if (selectedId == null) {
        armedGoogleFeatureIdRef.current = null;
        return;
      }

      const snapshot = (terraDrawRef.current?.getSnapshot() ??
        []) as TerraDrawFeature[];
      const selected = findTerraDrawFeature(snapshot, selectedId);
      if (shouldOpenShapePromptOnSelection(selected)) {
        armedGoogleFeatureIdRef.current = null;
        setOpen(true);
        return;
      }

      const mode = featureDrawMode(selected);
      if (
        (mode === "polygon" || mode === "linestring") &&
        isUserDrawnBoundaryShape(selected)
      ) {
        if (armedGoogleFeatureIdRef.current === selectedId) {
          armedGoogleFeatureIdRef.current = null;
          setOpen(true);
        } else {
          armedGoogleFeatureIdRef.current = selectedId;
        }
      }
    },
    [terraDrawRef],
  );

  const notifyFlatPolygonDrawn = notifyBoundaryDrawStarted;

  const notifyShapeSelected = useCallback(() => setOpen(true), []);

  const handleFlatBoundaryClick = useCallback(() => {
    setFlatBoundarySelected(true);
    setOpen(true);
  }, []);

  const deleteSelectedDrawing = useCallback(
    (syncAfterDelete?: (snapshot: TerraDrawFeature[]) => void) => {
      const draw = terraDrawRef.current;
      if (!draw) return;

      const remaining = deleteMainDrawnShape(draw, selectedFeatureIdRef.current);
      selectedFeatureIdRef.current = null;
      setSelectedFeatureId(null);
      armedGoogleFeatureIdRef.current = null;
      resetBoundaryDrawSession();
      syncAfterDelete?.(remaining);
      syncSnapshot(remaining);
    },
    [resetBoundaryDrawSession, syncSnapshot, terraDrawRef],
  );

  return {
    open,
    flatBoundarySelected,
    selectedFeatureId,
    openPrompt,
    closePrompt,
    handleSnapshotChange,
    handleChangeEvent,
    handleSelectionChange,
    notifyBoundaryDrawStarted,
    notifyFlatPolygonDrawn,
    notifyShapeSelected,
    handleFlatBoundaryClick,
    resetBoundaryDrawSession,
    deleteSelectedDrawing,
    hasDrawableBoundary: hasUserDrawnBoundaryShape,
  };
}
