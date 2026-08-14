import { describe, expect, it } from "vitest";
import {
  collectViolations,
  effectiveLines,
  evaluateAgainstBaseline,
  limitFor,
  pruneBaseline,
} from "./check_file_sizes.mjs";

describe("check_file_sizes", () => {
  it("counts non-comment source lines", () => {
    expect(effectiveLines("// comment\n\nconst x = 1;\n")).toBe(1);
  });

  it("applies stricter limits to views and hooks", () => {
    expect(limitFor("frontend/src/modules/field-survey/views/FieldPage.tsx")).toBe(180);
    expect(limitFor("frontend/src/modules/mission-runtime/hooks/useMissionRuntime.ts")).toBe(160);
    expect(limitFor("frontend/src/modules/warehouse/api/warehouseMissionsApi.ts")).toBe(220);
  });

  it("guards agriculture workflow modules at 400 lines", () => {
    expect(
      limitFor(
        "frontend/src/modules/agriculture/workflows/analysis/types.ts",
      ),
    ).toBe(400);
    expect(
      limitFor(
        "frontend/src/modules/agriculture/workflows/review/hooks.ts",
      ),
    ).toBe(400);
  });

  it("flags regressions and stale baseline entries", () => {
    const current = {
      "frontend/src/a.tsx": { effective_lines: 500, limit: 180 },
    };
    const baseline = {
      "frontend/src/a.tsx": { effective_lines: 480, limit: 180 },
      "frontend/src/removed.tsx": { effective_lines: 900, limit: 180 },
    };
    const { regressions, stale, grandfathered } = evaluateAgainstBaseline(current, baseline);
    expect(grandfathered).toBe(0);
    expect(stale).toEqual(["frontend/src/removed.tsx"]);
    expect(regressions).toHaveLength(1);
  });

  it("prunes resolved baseline entries", () => {
    const baseline = {
      "frontend/src/a.tsx": { effective_lines: 500, limit: 180 },
      "frontend/src/b.tsx": { effective_lines: 450, limit: 180 },
    };
    const current = {
      "frontend/src/a.tsx": { effective_lines: 500, limit: 180 },
    };
    expect(Object.keys(pruneBaseline(baseline, current))).toEqual(["frontend/src/a.tsx"]);
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
