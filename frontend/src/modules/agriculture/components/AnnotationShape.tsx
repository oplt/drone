import { memo } from "react";
import type Konva from "konva";
import type { KonvaEventObject } from "konva/lib/Node";
import { Label, Rect, Tag, Text } from "react-konva";
import {
  canvasBoxToImageBox,
  imageBoxToCanvasBox,
  type CanvasTransform,
  type ImageBox,
} from "../visionGeometry";
import type { AnnotationDraft } from "./annotationCanvasTypes";

type AnnotationShapeProps = {
  annotation: AnnotationDraft;
  transform: CanvasTransform;
  color: string;
  label: string;
  selected: boolean;
  editable: boolean;
  rectRef: (node: Konva.Rect | null) => void;
  onSelect: () => void;
  onCommit: (box: ImageBox) => void;
};

export const AnnotationShape = memo(function AnnotationShape({
  annotation,
  transform,
  color,
  label,
  selected,
  editable,
  rectRef,
  onSelect,
  onCommit,
}: AnnotationShapeProps) {
  const canvasBox = imageBoxToCanvasBox(annotation, transform);
  const commitNode = (node: Konva.Rect) => {
    const width = Math.max(1, node.width() * node.scaleX());
    const height = Math.max(1, node.height() * node.scaleY());
    node.scaleX(1);
    node.scaleY(1);
    onCommit(
      canvasBoxToImageBox(
        {
          x1: node.x(),
          y1: node.y(),
          x2: node.x() + width,
          y2: node.y() + height,
        },
        transform,
      ),
    );
  };
  return (
    <>
      <Rect
        ref={rectRef}
        name={`annotation-${annotation.id}`}
        x={canvasBox.x1}
        y={canvasBox.y1}
        width={canvasBox.x2 - canvasBox.x1}
        height={canvasBox.y2 - canvasBox.y1}
        fill={selected ? `${color}22` : undefined}
        stroke={color}
        strokeWidth={selected ? 3 : 2}
        draggable={editable}
        onClick={onSelect}
        onTap={onSelect}
        onDragEnd={(event: KonvaEventObject<DragEvent>) =>
          commitNode(event.target as Konva.Rect)
        }
        onTransformEnd={(event: KonvaEventObject<Event>) =>
          commitNode(event.target as Konva.Rect)
        }
      />
      <Label x={canvasBox.x1} y={Math.max(0, canvasBox.y1 - 23)} listening={false}>
        <Tag fill={color} cornerRadius={3} />
        <Text text={label.replaceAll("_", " ")} fill="#fff" fontSize={12} padding={5} />
      </Label>
    </>
  );
});
