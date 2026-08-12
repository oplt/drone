import { describe, expect, it } from "vitest";
import {
  canvasBoxToImageBox,
  canvasToImagePoint,
  clipImageBox,
  createFitTransform,
  imageBoxToCanvasBox,
  imageToCanvasPoint,
  imageToNormalizedBox,
  isValidImageBox,
  normalizedToImageBox,
  zoomAroundPoint,
} from "./visionGeometry";

describe("vision annotation geometry", () => {
  it("roundtrips high-resolution points through fit, zoom and pan", () => {
    const transform = {
      ...createFitTransform(7680, 4320, 1280, 720),
      zoom: 7.5,
      panX: -310,
      panY: 125,
    };
    const original = { x: 5112.125, y: 1208.75 };
    const restored = canvasToImagePoint(
      imageToCanvasPoint(original, transform),
      transform,
    );
    expect(restored.x).toBeCloseTo(original.x, 8);
    expect(restored.y).toBeCloseTo(original.y, 8);
  });

  it("roundtrips image boxes independently of viewport coordinates", () => {
    const transform = {
      ...createFitTransform(3840, 2160, 1100, 670),
      zoom: 2.25,
      panX: 87,
      panY: -43,
    };
    const box = { x1: 832, y1: 410, x2: 1180, y2: 864 };
    const restored = canvasBoxToImageBox(
      imageBoxToCanvasBox(box, transform),
      transform,
    );
    expect(restored).toEqual(expect.objectContaining(box));
  });

  it("clips, normalizes and restores boxes", () => {
    const clipped = clipImageBox(
      { x1: -10, y1: 20, x2: 4010, y2: 2300 },
      3840,
      2160,
    );
    expect(clipped).toEqual({ x1: 0, y1: 20, x2: 3840, y2: 2160 });
    const normalized = imageToNormalizedBox(clipped, 3840, 2160);
    expect(normalizedToImageBox(normalized, 3840, 2160)).toEqual(clipped);
  });

  it("rejects boxes below the minimum original-image size", () => {
    expect(isValidImageBox({ x1: 10, y1: 10, x2: 12, y2: 40 }, 3)).toBe(false);
    expect(isValidImageBox({ x1: 10, y1: 10, x2: 13, y2: 13 }, 3)).toBe(true);
  });

  it("keeps the image coordinate under the pointer fixed while zooming", () => {
    const transform = createFitTransform(4000, 3000, 1000, 700);
    const pointer = { x: 741, y: 318 };
    const before = canvasToImagePoint(pointer, transform);
    const after = canvasToImagePoint(
      pointer,
      zoomAroundPoint(transform, pointer, 4),
    );
    expect(after.x).toBeCloseTo(before.x, 8);
    expect(after.y).toBeCloseTo(before.y, 8);
  });
});
