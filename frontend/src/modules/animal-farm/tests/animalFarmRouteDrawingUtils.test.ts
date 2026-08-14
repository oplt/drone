import { describe, expect, it } from "vitest";
import {
  farmBorderFromTerraSnapshot,
  flatDrawModeForTool,
  googleTerraDrawModeForTool,
  shouldIgnoreGoogleMapClick,
  waypointsFromTerraSnapshot,
} from "../utils/animalFarmRouteDrawingUtils";

describe("animalFarmRouteDrawingUtils characterization", () => {
  it("extracts waypoints from terra point and linestring features", () => {
    const snapshot = [
      {
        id: "a",
        geometry: { type: "Point", coordinates: [4.35, 50.85] },
      },
      {
        id: "b",
        geometry: {
          type: "LineString",
          coordinates: [
            [4.36, 50.86],
            [4.37, 50.87],
          ],
        },
      },
    ];
    expect(waypointsFromTerraSnapshot(snapshot, 30)).toEqual([
      { lat: 50.85, lon: 4.35, alt: 30 },
      { lat: 50.86, lon: 4.36, alt: 30 },
      { lat: 50.87, lon: 4.37, alt: 30 },
    ]);
  });

  it("extracts farm border from polygon snapshot", () => {
    const snapshot = [
      {
        id: "border",
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [4.1, 50.1],
              [4.2, 50.2],
              [4.3, 50.3],
              [4.1, 50.1],
            ],
          ],
        },
      },
    ];
    expect(farmBorderFromTerraSnapshot(snapshot)).toEqual([
      [4.1, 50.1],
      [4.2, 50.2],
      [4.3, 50.3],
      [4.1, 50.1],
    ]);
  });

  it("maps route tool modes for google and flat engines", () => {
    expect(googleTerraDrawModeForTool("polyline")).toBe("linestring");
    expect(flatDrawModeForTool("polyline")).toBe("polyline");
  });

  it("ignores google map clicks while terra draw is active", () => {
    expect(shouldIgnoreGoogleMapClick("google", "point", "point")).toBe(true);
    expect(shouldIgnoreGoogleMapClick("google", "select", "point")).toBe(false);
    expect(shouldIgnoreGoogleMapClick("leaflet", "select", "none")).toBe(true);
  });
});
