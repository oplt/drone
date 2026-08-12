import type { VisionClass } from "../visionTypes";
import type { ImageBox } from "../visionGeometry";

export type AnnotationDraft = ImageBox & {
  id: string;
  class_id: string;
};

export type AnnotationTool = "select" | "draw" | "pan";

export type AnnotationCanvasHandle = {
  fit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  cancel: () => void;
};

export type AnnotationCanvasProps = {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  classes: VisionClass[];
  annotations: AnnotationDraft[];
  activeClassId: string | null;
  selectedId: string | null;
  tool: AnnotationTool;
  onSelect: (id: string | null) => void;
  onChange: (annotations: AnnotationDraft[]) => void;
  onZoomChange?: (zoom: number) => void;
};
