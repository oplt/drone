export type LabelingSaveState = "saved" | "saving" | "failed";

export type AnnotationConflict = {
  expectedRevision: number;
  currentRevision: number;
};
