import type { MutableRefObject } from "react";
import type { TerraDraw } from "terra-draw";
import { TerraDrawController, type TerraDrawEditorMode } from "../../maps";
import type { MissionMapEngine } from "../../maps";
import type { useMapShapeActionPrompt } from "../hooks/useMapShapeActionPrompt";

type ShapePrompt = Pick<
  ReturnType<typeof useMapShapeActionPrompt>,
  "handleSnapshotChange" | "handleChangeEvent" | "handleSelectionChange"
>;

export function WorkflowTerraDrawBridge({
  mapReady,
  mapRef,
  mapEngine,
  terraDrawMode,
  terraDrawRef,
  setTerraDrawReady,
  shapePrompt,
  onError,
}: {
  mapReady: boolean;
  mapRef: MutableRefObject<google.maps.Map | null>;
  mapEngine: MissionMapEngine;
  terraDrawMode: TerraDrawEditorMode;
  terraDrawRef: MutableRefObject<TerraDraw | null>;
  setTerraDrawReady: (ready: boolean) => void;
  shapePrompt: ShapePrompt;
  onError: (message: string) => void;
}) {
  return (
    <TerraDrawController
      map={mapReady ? mapRef.current : null}
      enabled={mapEngine === "google"}
      mode={terraDrawMode}
      drawRef={terraDrawRef}
      onReadyChange={setTerraDrawReady}
      onSnapshotChange={shapePrompt.handleSnapshotChange}
      onChangeEvent={shapePrompt.handleChangeEvent}
      onSelectionChange={shapePrompt.handleSelectionChange}
      onError={onError}
    />
  );
}
