import { describe, expect, it } from "vitest";
import { collectViolations, effectiveLines, limitFor } from "./check_file_sizes.mjs";

describe("check_file_sizes", () => {
  it("counts non-comment source lines", () => {
    expect(effectiveLines("// comment\n\nconst x = 1;\n")).toBe(1);
  });

  it("applies stricter limits to views and hooks", () => {
    expect(limitFor("frontend/src/modules/field-survey/views/FieldPage.tsx")).toBe(180);
    expect(limitFor("frontend/src/modules/mission-runtime/hooks/useMissionRuntime.ts")).toBe(160);
    expect(limitFor("frontend/src/modules/warehouse/api/warehouseMissionsApi.ts")).toBe(220);
  });

  it("matches recorded baseline violation count", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const baseline = JSON.parse(
      readFileSync(
        join(dirname(fileURLToPath(import.meta.url)), "file_size_baseline.json"),
        "utf8",
      ),
    );
    expect(Object.keys(collectViolations())).toEqual(Object.keys(baseline));
  });
});
