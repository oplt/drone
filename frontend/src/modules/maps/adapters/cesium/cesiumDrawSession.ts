import type * as Cesium from "cesium";
import { pickCartesianOnGlobe, cartesianToLngLat } from "./cesiumGlobePick";
import {
  completeShape,
  isFlatBoundaryDrawMode,
  shapePreview,
} from "../../utils/drawingShapes";
import { isNearLonLat } from "../../utils/flatMapShapeGeometry";
import type { DrawMode, DrawResult, LonLat } from "./cesiumMapTypes";

type AttachCesiumDrawHandlerArgs = {
  CesiumModule: typeof Cesium;
  viewer: Cesium.Viewer;
  drawMode: DrawMode;
  drawHandlerRef: { current: Cesium.ScreenSpaceEventHandler | null };
  drawAnchorsRef: { current: Cesium.Entity[] };
  drawTempEntityRef: { current: Cesium.Entity | null };
  drawFloatingPointRef: { current: Cesium.Entity | null };
  drawPositionsRef: { current: Cesium.Cartesian3[] };
  drawFreehandActiveRef: { current: boolean };
  drawIsActiveRef: { current: boolean };
  drawFloatingCartesianRef: { current: Cesium.Cartesian3 | null };
  drawModeRef: { current: DrawMode };
  onDrawCompleteRef: { current: ((res: DrawResult) => void) | undefined };
  onBoundaryDrawStartedRef: { current: (() => void) | undefined };
  onBoundaryDrawProgressRef: {
    current: ((coords: LonLat[]) => void) | undefined;
  };
};

function clearDrawEntities(args: AttachCesiumDrawHandlerArgs) {
  const { viewer, drawAnchorsRef, drawTempEntityRef, drawFloatingPointRef } =
    args;

  drawAnchorsRef.current.forEach((e) => viewer.entities.remove(e));
  drawAnchorsRef.current = [];

  if (drawTempEntityRef.current)
    viewer.entities.remove(drawTempEntityRef.current);
  drawTempEntityRef.current = null;

  if (drawFloatingPointRef.current)
    viewer.entities.remove(drawFloatingPointRef.current);
  drawFloatingPointRef.current = null;

  args.drawPositionsRef.current = [];
  args.drawFloatingCartesianRef.current = null;
  args.drawIsActiveRef.current = false;
  args.drawFreehandActiveRef.current = false;
}

function finishDraw(args: AttachCesiumDrawHandlerArgs, mode: DrawMode) {
  const {
    CesiumModule,
    drawFloatingCartesianRef,
    drawPositionsRef,
    onDrawCompleteRef,
  } = args;

  const floating = drawFloatingCartesianRef.current;
  let coords: [number, number][];

  if (
    (mode === "rectangle" || mode === "circle" || mode === "triangle") &&
    drawPositionsRef.current.length >= 1
  ) {
    const anchor = drawPositionsRef.current[0];
    const corner = floating ?? drawPositionsRef.current[1];
    if (!anchor || !corner) return;
    coords = [
      cartesianToLngLat(CesiumModule, anchor),
      cartesianToLngLat(CesiumModule, corner),
    ];
  } else {
    let pos = drawPositionsRef.current.slice();
    if (floating) pos = pos.filter((p) => p !== floating);
    coords = pos.map((p) => cartesianToLngLat(CesiumModule, p));
  }

  const result = completeShape(mode, coords);
  if (result) onDrawCompleteRef.current?.(result);

  clearDrawEntities(args);
}

export function attachCesiumDrawHandler(
  args: AttachCesiumDrawHandlerArgs,
): () => void {
  const {
    CesiumModule,
    viewer,
    drawMode,
    drawHandlerRef,
    drawAnchorsRef,
    drawTempEntityRef,
    drawFloatingPointRef,
    drawPositionsRef,
    drawFreehandActiveRef,
    drawIsActiveRef,
    drawFloatingCartesianRef,
    onDrawCompleteRef,
    onBoundaryDrawStartedRef,
    onBoundaryDrawProgressRef,
  } = args;

  try {
    drawHandlerRef.current?.destroy?.();
  } catch {}
  drawHandlerRef.current = null;

  clearDrawEntities(args);

  if (drawMode === "none") return () => {};

  viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(
    CesiumModule.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
  );

  const handler = new CesiumModule.ScreenSpaceEventHandler(viewer.scene.canvas);
  drawHandlerRef.current = handler;
  const canvas = viewer.scene.canvas;
  const preventContextMenu = (event: Event) => event.preventDefault();
  canvas.addEventListener("contextmenu", preventContextMenu);

  const ensureTempEntity = () => {
    if (drawTempEntityRef.current) return;

    const getPreviewCartesians = () => {
      const coords = drawPositionsRef.current.map((p) =>
        cartesianToLngLat(CesiumModule, p),
      );
      return shapePreview(drawMode, coords).map(([lng, lat]) =>
        CesiumModule.Cartesian3.fromDegrees(lng, lat),
      );
    };

    if (drawMode === "polyline") {
      drawTempEntityRef.current = viewer.entities.add({
        polyline: {
          positions: new CesiumModule.CallbackProperty(
            () => drawPositionsRef.current,
            false,
          ),
          width: 3,
          clampToGround: true,
        },
      });
    }

    if (
      ["polygon", "rectangle", "circle", "freehand", "triangle"].includes(
        drawMode,
      )
    ) {
      drawTempEntityRef.current = viewer.entities.add({
        polygon: {
          hierarchy: new CesiumModule.CallbackProperty(
            () => new CesiumModule.PolygonHierarchy(getPreviewCartesians()),
            false,
          ),
          material: CesiumModule.Color.YELLOW.withAlpha(0.25),
          outline: true,
          outlineColor: CesiumModule.Color.YELLOW,
        },
      });
    }
  };

  const addAnchor = (c: Cesium.Cartesian3) => {
    const ent = viewer.entities.add({
      position: c,
      point: {
        pixelSize: 10,
        color: CesiumModule.Color.YELLOW,
        outlineColor: CesiumModule.Color.BLACK,
        outlineWidth: 2,
      },
    });
    drawAnchorsRef.current.push(ent);
  };

  const committedDrawCoords = (): LonLat[] => {
    const floating = drawFloatingCartesianRef.current;
    let pos = drawPositionsRef.current.slice();
    if (floating) pos = pos.filter((p) => p !== floating);
    return pos.map((p) => cartesianToLngLat(CesiumModule, p));
  };

  const syncBoundaryDraw = (startedNew: boolean) => {
    if (!isFlatBoundaryDrawMode(drawMode)) return;
    if (startedNew) onBoundaryDrawStartedRef.current?.();
    const coords = committedDrawCoords();
    if (coords.length > 0) onBoundaryDrawProgressRef.current?.(coords);
  };

  handler.setInputAction((movement: any) => {
    const c = pickCartesianOnGlobe(viewer, CesiumModule, movement.position);
    if (!c) return;
    if (drawMode === "freehand") return;

    if (drawMode === "point") {
      addAnchor(c);
      onDrawCompleteRef.current?.({
        type: "point",
        coordinates: cartesianToLngLat(CesiumModule, c),
      });
      clearDrawEntities(args);
      return;
    }

    ensureTempEntity();

    if (
      drawMode === "rectangle" ||
      drawMode === "circle" ||
      drawMode === "triangle"
    ) {
      if (!drawIsActiveRef.current) {
        drawIsActiveRef.current = true;
        drawPositionsRef.current = [c, c.clone()];
        addAnchor(c);
        const floating = drawPositionsRef.current[1];
        drawFloatingCartesianRef.current = floating;
        drawFloatingPointRef.current = viewer.entities.add({
          position: floating,
          point: { pixelSize: 8, color: CesiumModule.Color.YELLOW },
        });
        syncBoundaryDraw(true);
        return;
      }
      const floating = drawFloatingCartesianRef.current;
      if (floating) {
        floating.x = c.x;
        floating.y = c.y;
        floating.z = c.z;
      }
      finishDraw(args, drawMode);
      return;
    }

    if (!drawIsActiveRef.current) {
      drawIsActiveRef.current = true;

      drawPositionsRef.current.push(c);
      addAnchor(c);

      const floating = c.clone();
      drawFloatingCartesianRef.current = floating;
      drawPositionsRef.current.push(floating);

      drawFloatingPointRef.current = viewer.entities.add({
        position: floating,
        point: { pixelSize: 8, color: CesiumModule.Color.YELLOW },
      });
      syncBoundaryDraw(true);
      return;
    }

    const floating = drawFloatingCartesianRef.current;
    if (floating) {
      drawPositionsRef.current = drawPositionsRef.current.filter(
        (p) => p !== floating,
      );
    }

    const committed = drawPositionsRef.current.map((p) =>
      cartesianToLngLat(CesiumModule, p),
    );
    const clickCoord = cartesianToLngLat(CesiumModule, c);
    if (
      (drawMode === "polygon" || drawMode === "polyline") &&
      committed.length >= 3 &&
      isNearLonLat(committed[0], clickCoord)
    ) {
      finishDraw(args, drawMode);
      return;
    }

    drawPositionsRef.current.push(c);
    addAnchor(c);

    const newFloating = c.clone();
    drawFloatingCartesianRef.current = newFloating;
    drawPositionsRef.current.push(newFloating);

    if (drawFloatingPointRef.current) {
      drawFloatingPointRef.current.position =
        new CesiumModule.ConstantPositionProperty(newFloating);
    }
    syncBoundaryDraw(false);
  }, CesiumModule.ScreenSpaceEventType.LEFT_CLICK);

  handler.setInputAction((movement: any) => {
    if (drawMode !== "freehand") return;
    const c = pickCartesianOnGlobe(viewer, CesiumModule, movement.position);
    if (!c) return;
    clearDrawEntities(args);
    drawFreehandActiveRef.current = true;
    drawIsActiveRef.current = true;
    drawPositionsRef.current = [c];
    ensureTempEntity();
    syncBoundaryDraw(true);
  }, CesiumModule.ScreenSpaceEventType.LEFT_DOWN);

  handler.setInputAction((movement: any) => {
    if (!drawIsActiveRef.current) return;

    if (drawMode !== "freehand") {
      const floating = drawFloatingCartesianRef.current;
      if (!floating) return;

      const c = pickCartesianOnGlobe(
        viewer,
        CesiumModule,
        movement.endPosition,
      );
      if (!c) return;

      floating.x = c.x;
      floating.y = c.y;
      floating.z = c.z;
      return;
    }

    if (!drawFreehandActiveRef.current) return;
    const c = pickCartesianOnGlobe(
      viewer,
      CesiumModule,
      movement.endPosition,
    );
    if (!c) return;
    const last =
      drawPositionsRef.current[drawPositionsRef.current.length - 1];
    if (last && CesiumModule.Cartesian3.distance(last, c) < 0.5) return;
    drawPositionsRef.current.push(c);
  }, CesiumModule.ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction(() => {
    if (drawMode !== "freehand" || !drawFreehandActiveRef.current) return;
    finishDraw(args, drawMode);
  }, CesiumModule.ScreenSpaceEventType.LEFT_UP);

  handler.setInputAction(() => {
    finishDraw(args, drawMode);
  }, CesiumModule.ScreenSpaceEventType.RIGHT_CLICK);
  handler.setInputAction(() => {
    finishDraw(args, drawMode);
  }, CesiumModule.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") clearDrawEntities(args);
    if (e.key === "Enter") finishDraw(args, drawMode);
  };
  window.addEventListener("keydown", onKey);

  return () => {
    window.removeEventListener("keydown", onKey);
    canvas.removeEventListener("contextmenu", preventContextMenu);
    try {
      handler.destroy();
    } catch {}
    drawHandlerRef.current = null;
    clearDrawEntities(args);
  };
}
