import {
  type ForwardedRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type Konva from "konva";
import type { KonvaEventObject } from "konva/lib/Node";
import {
  canvasToImagePoint,
  clipImageBox,
  createFitTransform,
  isValidImageBox,
  zoomAroundPoint,
  type ImageBox,
  type Point,
} from "../visionGeometry";
import type {
  AnnotationCanvasHandle,
  AnnotationCanvasProps,
} from "./annotationCanvasTypes";

function useHtmlImage(source: string): HTMLImageElement | null {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    const next = new window.Image();
    next.onload = () => setImage(next);
    next.src = source;
    return () => {
      next.onload = null;
    };
  }, [source]);
  return image;
}

export function useAnnotationCanvasController(
  props: AnnotationCanvasProps,
  ref: ForwardedRef<AnnotationCanvasHandle>,
) {
  const {
    imageUrl,
    imageWidth,
    imageHeight,
    annotations,
    activeClassId,
    selectedId,
    tool,
    onSelect,
    onChange,
    onZoomChange,
  } = props;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const transformerRef = useRef<Konva.Transformer | null>(null);
  const shapeRefs = useRef(new Map<string, Konva.Rect>());
  const drawingStart = useRef<Point | null>(null);
  const panStart = useRef<{ point: Point; panX: number; panY: number } | null>(null);
  const [viewport, setViewport] = useState({ width: 900, height: 620 });
  const [transform, setTransform] = useState(() =>
    createFitTransform(imageWidth, imageHeight, 900, 620),
  );
  const [drawing, setDrawing] = useState<ImageBox | null>(null);
  const image = useHtmlImage(imageUrl);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const update = () => {
      const bounds = container.getBoundingClientRect();
      setViewport({
        width: Math.max(320, bounds.width),
        height: Math.max(360, bounds.height),
      });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const fit = useCallback(() => {
    setTransform(createFitTransform(imageWidth, imageHeight, viewport.width, viewport.height));
    onZoomChange?.(1);
  }, [imageHeight, imageWidth, onZoomChange, viewport.height, viewport.width]);
  useEffect(() => fit(), [fit, imageUrl]);
  const setZoom = useCallback(
    (nextZoom: number, pointer = { x: viewport.width / 2, y: viewport.height / 2 }) => {
      setTransform((current) => {
        const next = zoomAroundPoint(current, pointer, nextZoom);
        onZoomChange?.(next.zoom);
        return next;
      });
    },
    [onZoomChange, viewport.height, viewport.width],
  );
  useImperativeHandle(
    ref,
    () => ({
      fit,
      zoomIn: () => setZoom(transform.zoom * 1.25),
      zoomOut: () => setZoom(transform.zoom / 1.25),
      cancel: () => {
        drawingStart.current = null;
        panStart.current = null;
        setDrawing(null);
      },
    }),
    [fit, setZoom, transform.zoom],
  );
  useEffect(() => {
    const selectedNode = selectedId ? shapeRefs.current.get(selectedId) : undefined;
    transformerRef.current?.nodes(selectedNode ? [selectedNode] : []);
    transformerRef.current?.getLayer()?.batchDraw();
  }, [annotations, selectedId, transform]);

  const pointerDown = (event: KonvaEventObject<MouseEvent | TouchEvent>) => {
    const stage = event.target.getStage();
    const point = stage?.getPointerPosition();
    if (!stage || !point) return;
    if (tool === "pan") {
      panStart.current = { point, panX: transform.panX, panY: transform.panY };
      return;
    }
    if (tool !== "draw" || !activeClassId || event.target !== stage) {
      if (event.target === stage) onSelect(null);
      return;
    }
    const imagePoint = canvasToImagePoint(point, transform);
    drawingStart.current = imagePoint;
    setDrawing({ x1: imagePoint.x, y1: imagePoint.y, x2: imagePoint.x, y2: imagePoint.y });
  };
  const pointerMove = (event: KonvaEventObject<MouseEvent | TouchEvent>) => {
    const point = event.target.getStage()?.getPointerPosition();
    if (!point) return;
    if (panStart.current) {
      const start = panStart.current;
      setTransform((current) => ({
        ...current,
        panX: start.panX + point.x - start.point.x,
        panY: start.panY + point.y - start.point.y,
      }));
    } else if (drawingStart.current) {
      const current = canvasToImagePoint(point, transform);
      setDrawing({
        x1: drawingStart.current.x,
        y1: drawingStart.current.y,
        x2: current.x,
        y2: current.y,
      });
    }
  };
  const pointerUp = () => {
    panStart.current = null;
    if (!drawing || !activeClassId) return;
    const clipped = clipImageBox(drawing, imageWidth, imageHeight);
    drawingStart.current = null;
    setDrawing(null);
    if (!isValidImageBox(clipped)) return;
    const id = crypto.randomUUID?.() ?? `annotation-${Date.now()}`;
    onChange([...annotations, { ...clipped, id, class_id: activeClassId }]);
    onSelect(id);
  };
  const commitAnnotation = useCallback(
    (id: string, nextBox: ImageBox) => {
      const clipped = clipImageBox(nextBox, imageWidth, imageHeight);
      if (isValidImageBox(clipped))
        onChange(annotations.map((item) => item.id === id ? { ...item, ...clipped } : item));
    },
    [annotations, imageHeight, imageWidth, onChange],
  );
  const registerShape = useCallback((id: string, node: Konva.Rect | null) => {
    if (node) shapeRefs.current.set(id, node);
    else shapeRefs.current.delete(id);
  }, []);
  return {
    containerRef,
    transformerRef,
    viewport,
    transform,
    drawing,
    image,
    setZoom,
    pointerDown,
    pointerMove,
    pointerUp,
    commitAnnotation,
    registerShape,
  };
}
