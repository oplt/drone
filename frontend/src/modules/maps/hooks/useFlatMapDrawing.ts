import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  completeShape,
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
}: UseFlatMapDrawingOptions) {
  const drawingRef = useRef<LonLat[]>([]);
  const freehandDrawingRef = useRef(false);
  const drawModeRef = useRef(drawMode);
  const onDrawCompleteRef = useRef(onDrawComplete);
  const onPickRef = useRef(onPickLatLng);
  const onPreviewRef = useRef(onPreview);
  const rafRef = useRef<number | null>(null);

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
    drawModeRef.current = drawMode;
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

  const finishDrawing = useCallback(() => {
    const mode = drawModeRef.current;
    const result = completeShape(mode, drawingRef.current);
    if (result) onDrawCompleteRef.current?.(result);
    drawingRef.current = [];
    freehandDrawingRef.current = false;
    previewNow(mode, []);
  }, [previewNow]);

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

      drawingRef.current = handleFlatMapShapeClick(
        mode,
        coord,
        drawingRef.current,
        (coords) => previewNow(mode, coords),
        finishDrawing,
      );
    },
    [finishDrawing, previewNow],
  );

  const startFreehand = useCallback(
    (coord: LonLat) => {
      if (drawModeRef.current !== "freehand") return false;
      freehandDrawingRef.current = true;
      drawingRef.current = [coord];
      previewNow("freehand", drawingRef.current);
      return true;
    },
    [previewNow],
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
        return;
      }

      if (mode !== "freehand" || !freehandDrawingRef.current) return;
      if (!shouldAppendFreehandPoint(drawingRef.current, coord)) return;
      drawingRef.current.push(coord);
      schedulePreview();
    },
    [schedulePreview],
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
