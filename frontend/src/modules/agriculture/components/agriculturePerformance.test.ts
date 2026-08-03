import { describe, expect, it } from "vitest";
import { indexAgricultureFeatures, reconnectBackoff } from "./agriculturePerformance";

describe("agriculture rendering and reconnect performance primitives", () => {
  it("indexes 5,000 observations in a bounded single pass", () => {
    const features = Array.from({ length: 5000 }, (_, index) => ({ properties: { id: index, severity: 0.5 } }));
    const start = performance.now();
    const indexed = indexAgricultureFeatures(features);
    expect(indexed).toHaveLength(5000);
    expect(performance.now() - start).toBeLessThan(250);
  });

  it("uses capped exponential backoff for realtime reconnect", () => {
    expect(reconnectBackoff(0)).toBe(500);
    expect(reconnectBackoff(8)).toBe(30000);
    expect(reconnectBackoff(99)).toBe(30000);
  });
});
