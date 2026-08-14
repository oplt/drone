import { describe, expect, it } from "vitest";
import { editableZoneRing, ringZoneGeometry } from "./interventionZoneGeometry";

describe("intervention zone geometry", () => {
  it("round-trips a drawable polygon and closes the ring", () => {
    const geometry = ringZoneGeometry([[4, 50], [4.1, 50], [4.1, 50.1]]);
    expect(geometry).toEqual({
      type: "Polygon",
      coordinates: [[[4, 50], [4.1, 50], [4.1, 50.1], [4, 50]]],
    });
    expect(editableZoneRing(geometry)).toHaveLength(4);
  });

  it("does not flatten a multipolygon into misleading editable geometry", () => {
    expect(editableZoneRing({ type: "MultiPolygon", coordinates: [] })).toBeNull();
  });
});
