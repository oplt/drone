import { describe, expect, it } from "vitest";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "./modelOptions";

describe("video analysis model options", () => {
  it("uses the better YOLO26 detector by default", () => {
    expect(DEFAULT_MODEL).toBe("yolo26s.pt");
  });

  it("includes built-in YOLO26 modes and local agriculture model only", () => {
    expect(MODEL_OPTIONS.map((option) => option.value)).toEqual([
      "yolo26n.pt",
      "yolo26s.pt",
      "yolo26n-seg.pt",
      "yolo26s-seg.pt",
      "storage/ml_models/agriculture/best.pt",
    ]);
  });
});
