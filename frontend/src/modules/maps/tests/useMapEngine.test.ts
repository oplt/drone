import { describe, expect, it } from "vitest";
import { dispatchMapEngineChange } from "../hooks/useMapEngine";

describe("useMapEngine", () => {
  it("dispatches engine change events", () => {
    let received: string | null = null;
    const handler = (event: Event) => {
      received = (event as CustomEvent<string>).detail;
    };
    window.addEventListener("mission-map-engine-change", handler);
    dispatchMapEngineChange("leaflet");
    window.removeEventListener("mission-map-engine-change", handler);
    expect(received).toBe("leaflet");
  });
});
