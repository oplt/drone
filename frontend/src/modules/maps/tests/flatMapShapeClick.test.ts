import { describe, expect, it } from "vitest";
import { handleFlatMapShapeClick } from "../utils/flatMapShapeClick";

describe("handleFlatMapShapeClick", () => {
  it("finishes polygon when clicking near the first point", () => {
    let finished = false;
    const drawing: [number, number][] = [
      [4.35, 50.85],
      [4.36, 50.85],
      [4.36, 50.86],
    ];

    const next = handleFlatMapShapeClick(
      "polygon",
      [4.350001, 50.850001],
      drawing,
      () => {},
      () => {
        finished = true;
      },
    );

    expect(finished).toBe(true);
    expect(next).toEqual([]);
  });

  it("finishes polyline when clicking near the first point with 3+ vertices", () => {
    let finished = false;

    handleFlatMapShapeClick(
      "polyline",
      [4.35, 50.85],
      [
        [4.35, 50.85],
        [4.36, 50.85],
        [4.36, 50.86],
      ],
      () => {},
      () => {
        finished = true;
      },
    );

    expect(finished).toBe(true);
  });
});
