import { describe, expect, it } from "vitest";
import MapProviders, { MapProviders as NamedMapProviders } from "./MapProviders";

describe("MapProviders", () => {
  it("exports the route-scoped provider as named and default", () => {
    expect(NamedMapProviders).toBe(MapProviders);
    expect(typeof MapProviders).toBe("function");
  });
});
