import { describe, expect, it } from "vitest";
import {
  assertShellHasNoMapPreloads,
  modulePreloadHrefs,
  unexpectedMapPreloads,
} from "./check_bundle_budgets.mjs";

describe("check_bundle_budgets", () => {
  it("allows ordinary application-shell preloads", () => {
    const html =
      '<link rel="modulepreload" href="/assets/vendor-mui-abcd.js">';
    expect(modulePreloadHrefs(html)).toEqual([
      "/assets/vendor-mui-abcd.js",
    ]);
    expect(() => assertShellHasNoMapPreloads(html)).not.toThrow();
  });

  it.each(["vendor-google-maps", "vendor-cesium", "cesium-widgets"])(
    "rejects a %s shell preload",
    (chunk) => {
      const html = `<link href="/assets/${chunk}-abcd.js" rel="modulepreload">`;
      expect(unexpectedMapPreloads(html)).toEqual([
        `/assets/${chunk}-abcd.js`,
      ]);
      expect(() => assertShellHasNoMapPreloads(html)).toThrow(
        "unexpectedly preloads",
      );
    },
  );
});
