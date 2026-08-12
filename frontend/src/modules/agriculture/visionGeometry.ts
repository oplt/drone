export type Point = { x: number; y: number };
export type ImageBox = { x1: number; y1: number; x2: number; y2: number };

export type CanvasTransform = {
  imageWidth: number;
  imageHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  fitScale: number;
  zoom: number;
  panX: number;
  panY: number;
};

export function createFitTransform(
  imageWidth: number,
  imageHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): CanvasTransform {
  const fitScale = Math.min(
    viewportWidth / imageWidth,
    viewportHeight / imageHeight,
  );
  return {
    imageWidth,
    imageHeight,
    viewportWidth,
    viewportHeight,
    fitScale: Number.isFinite(fitScale) && fitScale > 0 ? fitScale : 1,
    zoom: 1,
    panX: 0,
    panY: 0,
  };
}

export function effectiveScale(transform: CanvasTransform): number {
  return transform.fitScale * transform.zoom;
}

export function imageOrigin(transform: CanvasTransform): Point {
  const scale = effectiveScale(transform);
  return {
    x:
      (transform.viewportWidth - transform.imageWidth * scale) / 2 +
      transform.panX,
    y:
      (transform.viewportHeight - transform.imageHeight * scale) / 2 +
      transform.panY,
  };
}

export function imageToCanvasPoint(
  point: Point,
  transform: CanvasTransform,
): Point {
  const scale = effectiveScale(transform);
  const origin = imageOrigin(transform);
  return { x: origin.x + point.x * scale, y: origin.y + point.y * scale };
}

export function canvasToImagePoint(
  point: Point,
  transform: CanvasTransform,
): Point {
  const scale = effectiveScale(transform);
  const origin = imageOrigin(transform);
  return { x: (point.x - origin.x) / scale, y: (point.y - origin.y) / scale };
}

export function imageBoxToCanvasBox(
  box: ImageBox,
  transform: CanvasTransform,
): ImageBox {
  const start = imageToCanvasPoint({ x: box.x1, y: box.y1 }, transform);
  const end = imageToCanvasPoint({ x: box.x2, y: box.y2 }, transform);
  return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

export function canvasBoxToImageBox(
  box: ImageBox,
  transform: CanvasTransform,
): ImageBox {
  const start = canvasToImagePoint({ x: box.x1, y: box.y1 }, transform);
  const end = canvasToImagePoint({ x: box.x2, y: box.y2 }, transform);
  return normalizeBox({ x1: start.x, y1: start.y, x2: end.x, y2: end.y });
}

export function normalizeBox(box: ImageBox): ImageBox {
  return {
    x1: Math.min(box.x1, box.x2),
    y1: Math.min(box.y1, box.y2),
    x2: Math.max(box.x1, box.x2),
    y2: Math.max(box.y1, box.y2),
  };
}

export function clipImageBox(
  box: ImageBox,
  imageWidth: number,
  imageHeight: number,
): ImageBox {
  const normalized = normalizeBox(box);
  return {
    x1: Math.max(0, Math.min(imageWidth, normalized.x1)),
    y1: Math.max(0, Math.min(imageHeight, normalized.y1)),
    x2: Math.max(0, Math.min(imageWidth, normalized.x2)),
    y2: Math.max(0, Math.min(imageHeight, normalized.y2)),
  };
}

export function isValidImageBox(box: ImageBox, minimumSize = 3): boolean {
  return box.x2 - box.x1 >= minimumSize && box.y2 - box.y1 >= minimumSize;
}

export function normalizedToImageBox(
  box: ImageBox,
  width: number,
  height: number,
): ImageBox {
  return {
    x1: box.x1 * width,
    y1: box.y1 * height,
    x2: box.x2 * width,
    y2: box.y2 * height,
  };
}

export function imageToNormalizedBox(
  box: ImageBox,
  width: number,
  height: number,
): ImageBox {
  const clipped = clipImageBox(box, width, height);
  return {
    x1: clipped.x1 / width,
    y1: clipped.y1 / height,
    x2: clipped.x2 / width,
    y2: clipped.y2 / height,
  };
}

export function zoomAroundPoint(
  transform: CanvasTransform,
  pointer: Point,
  nextZoom: number,
): CanvasTransform {
  const clampedZoom = Math.max(0.1, Math.min(16, nextZoom));
  const imagePoint = canvasToImagePoint(pointer, transform);
  const next = { ...transform, zoom: clampedZoom };
  const projected = imageToCanvasPoint(imagePoint, next);
  return {
    ...next,
    panX: next.panX + pointer.x - projected.x,
    panY: next.panY + pointer.y - projected.y,
  };
}
