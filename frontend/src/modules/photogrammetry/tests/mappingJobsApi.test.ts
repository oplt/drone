import { describe, expect, it } from "vitest";
import { FAST_3D_MAP_WEBODM_OPTIONS } from "../types";

describe("photogrammetry types", () => {
  it("keeps fast 3d map defaults stable", () => {
    expect(FAST_3D_MAP_WEBODM_OPTIONS["use-3dmesh"]).toBe(true);
    expect(FAST_3D_MAP_WEBODM_OPTIONS["mesh-size"]).toBe(100000);
  });
});
