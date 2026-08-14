import { useEffect } from "react";
import { attachCesiumDrawHandler } from "../adapters/cesium/cesiumDrawSession";
import type { DrawMode } from "../adapters/cesium/cesiumMapTypes";
import type { CesiumMapRefs } from "./useCesiumMapRefs";

export function useCesiumDrawSession(refs: CesiumMapRefs, drawMode: DrawMode) {
  useEffect(() => {
    const CesiumModule = refs.cesiumRef.current;
    const viewer = refs.viewerRef.current;
    if (!CesiumModule || !viewer) return;

    return attachCesiumDrawHandler({
      CesiumModule,
      viewer,
      drawMode,
      drawHandlerRef: refs.drawHandlerRef,
      drawAnchorsRef: refs.drawAnchorsRef,
      drawTempEntityRef: refs.drawTempEntityRef,
      drawFloatingPointRef: refs.drawFloatingPointRef,
      drawPositionsRef: refs.drawPositionsRef,
      drawFreehandActiveRef: refs.drawFreehandActiveRef,
      drawIsActiveRef: refs.drawIsActiveRef,
      drawFloatingCartesianRef: refs.drawFloatingCartesianRef,
      drawModeRef: refs.drawModeRef,
      onDrawCompleteRef: refs.onDrawCompleteRef,
      onBoundaryDrawStartedRef: refs.onBoundaryDrawStartedRef,
      onBoundaryDrawProgressRef: refs.onBoundaryDrawProgressRef,
    });
  }, [drawMode, refs]);
}
