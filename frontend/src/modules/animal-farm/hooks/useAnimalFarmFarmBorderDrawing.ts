import { useCallback, useMemo, useRef, useState } from "react";
import type { TerraDraw } from "terra-draw";
import { useFields, FIELD_WORKFLOW_SCOPES, type LonLat } from "../../fields";
import { createFarmBorderDrawBridge } from "../../maps/utils/flatBoundaryDrawBridge";
import type { TerraDrawFeature } from "../../maps";
import { useMapShapeActionPrompt } from "../../mission-workflow";
import { farmBorderFromTerraSnapshot } from "../utils/animalFarmRouteDrawingUtils";

type UseAnimalFarmFarmBorderDrawingOptions = {
  addError: (message: string) => void;
};

export function useAnimalFarmFarmBorderDrawing({ addError }: UseAnimalFarmFarmBorderDrawingOptions) {
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const [farmBorder, setFarmBorder] = useState<LonLat[] | null>(null);
  const [farmBorderName, setFarmBorderName] = useState("Pasture A");
  const { createField: createFarmBorderRecord, saving: savingFarmBorder } = useFields(
    FIELD_WORKFLOW_SCOPES.animalFarm,
  );

  const syncFarmBorderFromSnapshot = useCallback((snapshot: TerraDrawFeature[]) => {
    setFarmBorder(farmBorderFromTerraSnapshot(snapshot));
  }, []);

  const shapePrompt = useMapShapeActionPrompt({
    terraDrawRef,
    syncSnapshot: syncFarmBorderFromSnapshot,
  });

  const farmBorderDraw = useMemo(
    () =>
      createFarmBorderDrawBridge({
        setFarmBorder,
        onBoundaryDrawStarted: shapePrompt.notifyBoundaryDrawStarted,
      }),
    [shapePrompt.notifyBoundaryDrawStarted],
  );

  const handleFarmBorderSave = useCallback(async () => {
    if (!farmBorder || farmBorder.length < 3) {
      addError("Draw a farm border polygon (min 3 points) before saving.");
      return;
    }
    if (!farmBorderName.trim()) {
      addError("Please enter a border name.");
      return;
    }
    try {
      await createFarmBorderRecord({
        name: farmBorderName.trim(),
        coordinates: farmBorder,
      });
      shapePrompt.closePrompt();
    } catch (error: unknown) {
      addError(error instanceof Error ? error.message : "Failed to save farm border");
    }
  }, [addError, createFarmBorderRecord, farmBorder, farmBorderName, shapePrompt]);

  return {
    terraDrawRef,
    farmBorder,
    setFarmBorder,
    farmBorderName,
    setFarmBorderName,
    savingFarmBorder,
    shapePrompt,
    farmBorderDraw,
    syncFarmBorderFromSnapshot,
    handleFarmBorderSave,
  };
}
