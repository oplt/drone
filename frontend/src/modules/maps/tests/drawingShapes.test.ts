import { describe, expect, it } from "vitest";
import { moveTwoCornerShapePreview } from "../utils/drawingShapes";

describe("moveTwoCornerShapePreview", () => {
  it.each(["rectangle", "circle", "triangle"] as const)(
    "keeps the starting corner while the %s cursor endpoint continues moving",
    (mode) => {
      const start: [number, number] = [4.3, 50.8];
      const firstMove = moveTwoCornerShapePreview(mode, [start], [4.31, 50.81]);
      const secondMove = moveTwoCornerShapePreview(mode, firstMove ?? [], [4.32, 50.82]);

      expect(firstMove).toEqual([start, [4.31, 50.81]]);
      expect(secondMove).toEqual([start, [4.32, 50.82]]);
    },
  );

  it("does not produce a moving endpoint before drawing begins", () => {
    expect(moveTwoCornerShapePreview("rectangle", [], [4.31, 50.81])).toBeNull();
    expect(moveTwoCornerShapePreview("polygon", [[4.3, 50.8]], [4.31, 50.81])).toBeNull();
  });
});
