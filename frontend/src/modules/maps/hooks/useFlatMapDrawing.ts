import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  completeShape,
  isFlatBoundaryDrawMode,
  moveTwoCornerShapePreview,
  type LonLat,
  type ShapeDrawMode,
  type ShapeDrawResult,
} from "../utils/drawingShapes";
import { handleFlatMapShapeClick } from "../utils/flatMapShapeClick";

const MIN_FREEHAND_DELTA_DEG = 0.000005;

type LatLng = { lat: number; lng: number };

type UseFlatMapDrawingOptions = {
  drawMode: ShapeDrawMode;
  onDrawComplete?: (result: ShapeDrawResult) => void;
  onPickLatLng?: (point: LatLng) => void;
  onPreview: (mode: ShapeDrawMode, coords: LonLat[]) => void;
  onModeStateChange?: (mode: ShapeDrawMode) => void;
  onBoundaryDrawStarted?: () => void;
  onBoundaryDrawProgress?: (coords: LonLat[]) => void;
  isNearCoord?: (a: LonLat, b: LonLat) => boolean;
};

function shouldAppendFreehandPoint(points: LonLat[], next: LonLat) {
  const prev = points[points.length - 1];
  if (!prev) return true;
  return (
    Math.abs(prev[0] - next[0]) >= MIN_FREEHAND_DELTA_DEG ||
    Math.abs(prev[1] - next[1]) >= MIN_FREEHAND_DELTA_DEG
  );
}

export function useFlatMapDrawing({
  drawMode,
  onDrawComplete,
  onPickLatLng,
  onPreview,
  onModeStateChange,
  onBoundaryDrawStarted,
  onBoundaryDrawProgress,
  isNearCoord,
}: UseFlatMapDrawingOptions) {
  const drawingRef = useRef<LonLat[]>([]);
  const freehandDrawingRef = useRef(false);
  const drawModeRef = useRef(drawMode);
  const onDrawCompleteRef = useRef(onDrawComplete);
  const onPickRef = useRef(onPickLatLng);
  const onPreviewRef = useRef(onPreview);
  const onBoundaryDrawStartedRef = useRef(onBoundaryDrawStarted);
  const onBoundaryDrawProgressRef = useRef(onBoundaryDrawProgress);
  const isNearCoordRef = useRef(isNearCoord);
  const rafRef = useRef<number | null>(null);
  const previousDrawModeRef = useRef(drawMode);

  drawModeRef.current = drawMode;

  const flushPreview = useCallback(() => {
    rafRef.current = null;
    onPreviewRef.current(drawModeRef.current, drawingRef.current);
  }, []);

  const schedulePreview = useCallback(() => {
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(flushPreview);
  }, [flushPreview]);

  const previewNow = useCallback((mode: ShapeDrawMode, coords: LonLat[]) => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    onPreviewRef.current(mode, coords);
  }, []);

  const syncBoundaryDrawState = useCallback((mode: ShapeDrawMode, coords: LonLat[]) => {
    if (!isFlatBoundaryDrawMode(mode) || coords.length === 0) return;
    onBoundaryDrawProgressRef.current?.(coords);
  }, []);

  const maybeStartBoundaryDraw = useCallback((mode: ShapeDrawMode, wasEmpty: boolean) => {
    if (!wasEmpty || !isFlatBoundaryDrawMode(mode)) return;
    onBoundaryDrawStartedRef.current?.();
  }, []);

  useEffect(() => {
    onPickRef.current = onPickLatLng;
  }, [onPickLatLng]);

  useEffect(() => {
    onDrawCompleteRef.current = onDrawComplete;
  }, [onDrawComplete]);

  useEffect(() => {
    onPreviewRef.current = onPreview;
  }, [onPreview]);

  useEffect(() => {
    onBoundaryDrawStartedRef.current = onBoundaryDrawStarted;
  }, [onBoundaryDrawStarted]);

  useEffect(() => {
    onBoundaryDrawProgressRef.current = onBoundaryDrawProgress;
  }, [onBoundaryDrawProgress]);

  useEffect(() => {
    isNearCoordRef.current = isNearCoord;
  }, [isNearCoord]);

  useEffect(() => {
    if (previousDrawModeRef.current === drawMode) return;
    previousDrawModeRef.current = drawMode;
    drawingRef.current = [];
    freehandDrawingRef.current = false;
    previewNow(drawMode, []);
    onModeStateChange?.(drawMode);
  }, [drawMode, onModeStateChange, previewNow]);

  useEffect(
    () => () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    },
    [],
  );

  const finishDrawing = useCallback(
    (coordsOverride?: LonLat[]) => {
      const mode = drawModeRef.current;
      const coords = coordsOverride ?? drawingRef.current;
      const result = completeShape(mode, coords);
      if (result) onDrawCompleteRef.current?.(result);
      drawingRef.current = [];
      freehandDrawingRef.current = false;
      previewNow(mode, []);
    },
    [previewNow],
  );

  const handleClick = useCallback(
    (coord: LonLat) => {
      const mode = drawModeRef.current;
      if (mode === "none") {
        onPickRef.current?.({ lat: coord[1], lng: coord[0] });
        return;
      }

      if (mode === "point") {
        onDrawCompleteRef.current?.({ type: "point", coordinates: coord });
        return;
      }

      if (mode === "freehand") return;

      const wasEmpty = drawingRef.current.length === 0;
      drawingRef.current = handleFlatMapShapeClick(
        mode,
        coord,
        drawingRef.current,
        (coords) => previewNow(mode, coords),
        (coords) => finishDrawing(coords),
        isNearCoordRef.current,
      );
      maybeStartBoundaryDraw(mode, wasEmpty);
      syncBoundaryDrawState(mode, drawingRef.current);
    },
    [finishDrawing, maybeStartBoundaryDraw, previewNow, syncBoundaryDrawState],
  );

  const startFreehand = useCallback(
    (coord: LonLat) => {
      if (drawModeRef.current !== "freehand") return false;
      const wasEmpty = drawingRef.current.length === 0;
      freehandDrawingRef.current = true;
      drawingRef.current = [coord];
      previewNow("freehand", drawingRef.current);
      maybeStartBoundaryDraw("freehand", wasEmpty);
      syncBoundaryDrawState("freehand", drawingRef.current);
      return true;
    },
    [maybeStartBoundaryDraw, previewNow, syncBoundaryDrawState],
  );

  const movePointer = useCallback(
    (coord: LonLat) => {
      const mode = drawModeRef.current;
      const twoCornerPreview = moveTwoCornerShapePreview(
        mode,
        drawingRef.current,
        coord,
      );
      if (twoCornerPreview) {
        drawingRef.current = twoCornerPreview;
        schedulePreview();
        syncBoundaryDrawState(mode, drawingRef.current);
        return;
      }

      if (mode !== "freehand" || !freehandDrawingRef.current) return;
      if (!shouldAppendFreehandPoint(drawingRef.current, coord)) return;
      drawingRef.current.push(coord);
      schedulePreview();
      syncBoundaryDrawState(mode, drawingRef.current);
    },
    [schedulePreview, syncBoundaryDrawState],
  );

  const endFreehand = useCallback(() => {
    if (drawModeRef.current !== "freehand" || !freehandDrawingRef.current)
      return false;
    finishDrawing();
    return true;
  }, [finishDrawing]);

  return useMemo(
    () => ({
      finishDrawing,
      handleClick,
      startFreehand,
      movePointer,
      endFreehand,
    }),
    [endFreehand, finishDrawing, handleClick, movePointer, startFreehand],
  );
}
