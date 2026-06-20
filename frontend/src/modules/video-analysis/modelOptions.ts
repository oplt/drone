import type { AnalyzeVideoPayload } from "./types";

export const DEFAULT_MODEL: AnalyzeVideoPayload["model_name"] = "yolo26s.pt";

export const MODEL_OPTIONS: ReadonlyArray<{
  value: AnalyzeVideoPayload["model_name"];
  label: string;
}> = [
  { value: "yolo26n.pt", label: "YOLO26n · fastest detector" },
  { value: "yolo26s.pt", label: "YOLO26s · better/default detector" },
  { value: "yolo26n-seg.pt", label: "YOLO26n-seg · fast segmentation" },
  { value: "yolo26s-seg.pt", label: "YOLO26s-seg · better segmentation" },
  {
    value: "backend/storage/ml_models/agriculture/best.pt",
    label: "Custom agriculture best.pt",
  },
];
