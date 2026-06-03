import { describe, expect, it } from "vitest";
import { extractLatLng } from "./extractLatLng";

describe("extractLatLng", () => {
  it("extracts coordinates from legacy telemetry position", () => {
    expect(extractLatLng({ position: { lat: 50.85, lon: 4.35 } })).toEqual({
      lat: 50.85,
      lng: 4.35,
    });
  });

  it("extracts coordinates from nested websocket envelopes", () => {
    expect(
      extractLatLng({
        type: "telemetry",
        data: { position: { lat: "50.85", lon: "4.35" } },
      }),
    ).toEqual({ lat: 50.85, lng: 4.35 });

    expect(
      extractLatLng({
        payload: { position: { latitude: "50.86", longitude: "4.36" } },
      }),
    ).toEqual({ lat: 50.86, lng: 4.36 });
  });

  it("rejects empty null-island positions", () => {
    expect(extractLatLng({ position: { lat: 0, lon: 0 } })).toBeNull();
  });
});
