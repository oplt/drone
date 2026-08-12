import { forwardRef, useMemo } from "react";
import { Box } from "@mui/material";
import type { KonvaEventObject } from "konva/lib/Node";
import { Image as KonvaImage, Layer, Rect, Stage, Transformer } from "react-konva";
import { classColor } from "../visionColors";
import { imageBoxToCanvasBox, imageOrigin, type ImageBox } from "../visionGeometry";
import { useAnnotationCanvasController } from "./AnnotationCanvasController";
import { AnnotationShape } from "./AnnotationShape";
import type {
  AnnotationCanvasHandle,
  AnnotationCanvasProps,
} from "./annotationCanvasTypes";

export type {
  AnnotationCanvasHandle,
  AnnotationCanvasProps,
  AnnotationDraft,
  AnnotationTool,
} from "./annotationCanvasTypes";

type TransformerBox = {
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
};

export const AnnotationCanvas = forwardRef<AnnotationCanvasHandle, AnnotationCanvasProps>(
  function AnnotationCanvas(props, ref) {
    const {
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
    } = useAnnotationCanvasController(props, ref);
    const classById = useMemo(
      () => new Map(props.classes.map((visionClass) => [visionClass.id, visionClass])),
      [props.classes],
    );
    const origin = imageOrigin(transform);
    const scale = transform.fitScale * transform.zoom;
    const drawingCanvas = drawing
      ? imageBoxToCanvasBox(drawing, transform)
      : null;
    return (
      <Box
        ref={containerRef}
        data-testid="annotation-canvas"
        sx={{ width: "100%", height: "100%", minHeight: 360, overflow: "hidden", bgcolor: "#121714" }}
      >
        <Stage
          width={viewport.width}
          height={viewport.height}
          onMouseDown={pointerDown}
          onMouseMove={pointerMove}
          onMouseUp={pointerUp}
          onTouchStart={pointerDown}
          onTouchMove={pointerMove}
          onTouchEnd={pointerUp}
          onWheel={(event: KonvaEventObject<WheelEvent>) => {
            event.evt.preventDefault();
            const pointer = event.target.getStage()?.getPointerPosition();
            if (pointer)
              setZoom(
                transform.zoom * (event.evt.deltaY > 0 ? 0.85 : 1.18),
                pointer,
              );
          }}
          style={{ cursor: props.tool === "draw" ? "crosshair" : props.tool === "pan" ? "grab" : "default" }}
        >
          <Layer listening={false}>
            {image ? (
              <KonvaImage
                image={image}
                x={origin.x}
                y={origin.y}
                width={props.imageWidth * scale}
                height={props.imageHeight * scale}
              />
            ) : null}
          </Layer>
          <Layer>
            {props.annotations.map((annotation) => (
              <AnnotationShape
                key={annotation.id}
                annotation={annotation}
                transform={transform}
                color={classColor(annotation.class_id)}
                label={classById.get(annotation.class_id)?.name ?? "unknown"}
                selected={props.selectedId === annotation.id}
                editable={props.tool === "select"}
                rectRef={(node) => registerShape(annotation.id, node)}
                onSelect={() => props.onSelect(annotation.id)}
                onCommit={(box: ImageBox) => commitAnnotation(annotation.id, box)}
              />
            ))}
            <Transformer
              ref={transformerRef}
              rotateEnabled={false}
              flipEnabled={false}
              resizeEnabled={props.tool === "select"}
              anchorSize={9}
              borderStroke="#fff"
              anchorFill="#fff"
              boundBoxFunc={(oldBox: TransformerBox, newBox: TransformerBox) =>
                newBox.width < 6 || newBox.height < 6 ? oldBox : newBox
              }
            />
          </Layer>
          <Layer listening={false}>
            {drawingCanvas ? (
              <Rect
                x={Math.min(drawingCanvas.x1, drawingCanvas.x2)}
                y={Math.min(drawingCanvas.y1, drawingCanvas.y2)}
                width={Math.abs(drawingCanvas.x2 - drawingCanvas.x1)}
                height={Math.abs(drawingCanvas.y2 - drawingCanvas.y1)}
                stroke={classColor(props.activeClassId ?? "")}
                strokeWidth={2}
                dash={[8, 4]}
              />
            ) : null}
          </Layer>
        </Stage>
      </Box>
    );
  },
);
